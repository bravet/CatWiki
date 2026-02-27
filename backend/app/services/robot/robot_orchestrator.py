import asyncio
import logging
import threading
import time
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import BackgroundTasks

from app.core.integration.robot.base import BaseRobotAdapter, RobotSession
from app.schemas.chat import ChatCompletionRequest
from app.schemas.document import VectorRetrieveFilter
from app.services.chat.chat_service import ChatService

logger = logging.getLogger(__name__)


class RobotOrchestrator:
    """机器人通用消息处理（充当 Orchestrator 角色）。"""

    DEFAULT_ERROR_REPLY = "服务暂时繁忙，请稍后再试。"
    DEFAULT_TIMEOUT_REPLY = "服务响应超时，请稍后再试。"
    DEFAULT_EMPTY_REPLY = "抱歉，我暂时无法回答这个问题。"

    _global_locks: dict[str, float] = {}  # thread_id -> start_time
    _global_lock_mutex = threading.Lock()

    @classmethod
    async def orchestrate_reply(
        cls,
        *,
        adapter: BaseRobotAdapter,
        session: RobotSession,
        background_tasks: BackgroundTasks | None = None,
    ) -> None:
        """
        核心编排逻辑：流式 AI 推理 + 实时推送 + 异常处理。
        """
        provider = adapter.get_provider_name()
        provider_id = adapter.get_provider_id()
        thread_id = cls._get_thread_id(provider_id, session.event.from_user, session.event.chat_id)
        content = session.event.content.strip()

        # 1. 指令预处理 (全局通用)
        if content.lower() in ["/clear", "重置", "清空对话"]:
            logger.info("🧹 [%s] 指令触发: 重置对话 thread_id=%s", provider, thread_id)
            # 强制清理锁
            with cls._global_lock_mutex:
                cls._global_locks.pop(thread_id, None)

            from app.services.chat.session_service import ChatSessionService
            from app.db.database import AsyncSessionLocal

            async with AsyncSessionLocal() as db:
                await ChatSessionService.delete_by_thread_id(db, thread_id)

            await adapter.reply(
                session, "✅ 已为您清空对话上下文，现在可以开始新的咨询了。", is_finish=True
            )
            return

        # 2. 全局并发锁：防止同一线程并发 AI 任务
        with cls._global_lock_mutex:
            # 清理过期的锁 (超过 10 分钟认为已挂掉)
            now = time.time()
            expired_threads = [tid for tid, ts in cls._global_locks.items() if now - ts > 600]
            for tid in expired_threads:
                cls._global_locks.pop(tid, None)

            if thread_id in cls._global_locks:
                logger.warning(
                    "⏳ [%s] 并发任务拦截: thread_id=%s 已有任务在运行", provider, thread_id
                )
                # 对于非 Pull 模式的平台，可以选择不回复或发送提醒
                # 我们这里选择发送一个轻微提醒（如果适配器支持更新/发送）
                try:
                    await adapter.reply(session, "正在为您写答案，请稍候...", is_finish=False)
                except Exception:
                    pass
                return

            # 加锁
            cls._global_locks[thread_id] = now

        full_answer = ""
        start_time = time.time()
        last_sync_time = start_time
        sync_count = 0
        token_count = 0
        # 获取平台建议的同步间隔
        sync_interval = adapter.get_sync_interval()

        try:
            # 1. 发送初始状态（如飞书发送空白卡片）
            await adapter.reply(session, "", is_finish=False)

            if adapter.is_streaming_supported(session):
                # 2. 启动流式推理
                async for chunk in cls.stream_ask(
                    provider=provider,
                    site_id=session.event.site_id,
                    thread_id=thread_id,
                    user=session.event.from_user,
                    content=session.event.content,
                    background_tasks=background_tasks,
                ):
                    token_count += 1
                    full_answer += chunk

                    # 3. 节流推送到适配器
                    now = time.time()
                    if now - last_sync_time >= sync_interval:
                        try:
                            await adapter.reply(session, full_answer, is_finish=False)
                            last_sync_time = now
                            sync_count += 1
                        except Exception as e:
                            logger.warning("%s 流式更新失败 (待下次重试): %s", provider, e)
            else:
                # 不支持流式的平台（如企微内部应用/企微客服），走非流式一次性拉取，速度更快
                full_answer = await cls.ask(
                    provider=provider,
                    site_id=session.event.site_id,
                    thread_id=thread_id,
                    user=session.event.from_user,
                    content=session.event.content,
                    background_tasks=background_tasks,
                )
                token_count = len(full_answer)

            # 4. 最终全量更新
            await adapter.reply(session, full_answer, is_finish=True)
            sync_count += 1

            total_duration = time.time() - start_time
            logger.info(
                "🚀 %s 消息编排完成: 总耗时=%.2fs, 推理模式=%s, 同步次数=%d",
                provider,
                total_duration,
                "Stream" if adapter.is_streaming_supported(session) else "Block",
                sync_count,
            )

        except Exception as e:
            logger.exception("%s 消息编排异常: %s", provider, e)
            try:
                await adapter.reply(session, full_answer, is_error=True)
            except Exception:
                logger.error("%s 错误状态更新失败", provider)
        finally:
            # Note: background_tasks is handled by FastAPI, no need to await/call it here.
            # 释放锁
            with cls._global_lock_mutex:
                cls._global_locks.pop(thread_id, None)

    @classmethod
    async def ask(
        cls,
        *,
        provider: str,
        site_id: int,
        thread_id: str,
        user: str,
        content: str,
        background_tasks: BackgroundTasks | None = None,
        timeout_seconds: int = 90,
    ) -> str:
        chat_request = ChatCompletionRequest(
            message=content,
            thread_id=thread_id,
            user=user,
            stream=False,
            filter=VectorRetrieveFilter(site_id=site_id),
        )

        answer = cls.DEFAULT_EMPTY_REPLY
        try:
            response = await asyncio.wait_for(
                ChatService.process_chat_request(
                    chat_request, background_tasks or BackgroundTasks()
                ),
                timeout=timeout_seconds,
            )
            msg = cls._extract_first_message_content(response)
            if msg:
                answer = msg
        except TimeoutError:
            logger.error("%s AI 推理超时（%ss）: site_id=%s", provider, timeout_seconds, site_id)
            answer = cls.DEFAULT_TIMEOUT_REPLY
        except Exception as e:
            logger.error("%s AI 推理失败: %s", provider, e, exc_info=True)
            answer = cls.DEFAULT_ERROR_REPLY
        return answer

    @classmethod
    async def stream_ask(
        cls,
        *,
        provider: str,
        site_id: int,
        thread_id: str,
        user: str,
        content: str,
        background_tasks: BackgroundTasks | None = None,
    ) -> AsyncGenerator[str, None]:
        """流式获取消息内容（直接获取纯文本碎片，不再通过 SSE 解析）。"""
        from app.core.ai.graph import create_agent_graph
        from app.core.ai.graph.checkpointer import get_checkpointer
        from app.schemas.chat import ChatCompletionChunk

        background_tasks = background_tasks or BackgroundTasks()

        try:
            # 1. 使用 ChatService 统一初始化上下文 (llm, 初始状态, 数据库持久化等)
            llm, initial_state, config, _ = await ChatService.initialize_chat_context(
                thread_id=thread_id,
                site_id=site_id,
                user_id=user,
                message=content,
            )

            # 2. 启动流式推理并直接 yield 文本

            async with get_checkpointer() as cp:
                graph = create_agent_graph(checkpointer=cp, model=llm)
                async for chunk in ChatService.generate_chat_chunks(
                    graph, initial_state, config, llm.model_name, thread_id, background_tasks
                ):
                    if isinstance(chunk, ChatCompletionChunk):
                        content_piece = chunk.choices[0].delta.content
                        if content_piece:
                            logger.debug("AI 产出 Token 片段: len=%d", len(content_piece))
                            yield content_piece
        except Exception as e:
            logger.error("%s AI 流式推理失败: %s", provider, e, exc_info=True)
            yield cls.DEFAULT_ERROR_REPLY

    @staticmethod
    def _get_thread_id(provider_id: str, from_user: str, chat_id: str | None = None) -> str:
        """统一生成机器人会话 ID"""
        target = chat_id or from_user
        return f"{provider_id}-robot-{target}"

    @staticmethod
    def _extract_first_message_content(response: Any) -> str | None:
        if not hasattr(response, "choices") or not response.choices:
            return None
        msg = response.choices[0].message
        if not msg or not msg.content:
            return None
        return msg.content
