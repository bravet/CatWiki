# Copyright 2026 CatWiki Authors
#
# Licensed under the CatWiki Open Source License (Modified Apache 2.0);
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://github.com/CatWiki/CatWiki/blob/main/LICENSE
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import json
import logging
import time
import uuid
from collections.abc import AsyncGenerator

from fastapi import BackgroundTasks
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_openai import ChatOpenAI

from app.core.ai.graph import create_agent_graph
from app.core.ai.graph.checkpointer import get_checkpointer
from app.core.ai.providers.llm_manager import llm_manager
from app.core.vector.rag_utils import (
    convert_tool_call_chunk_to_openai,
    extract_sources_from_messages,
)
from app.crud import crud_site
from app.db.database import AsyncSessionLocal
from app.schemas.chat import (
    ChatCompletionChoice,
    ChatCompletionChunk,
    ChatCompletionChunkChoice,
    ChatCompletionChunkDelta,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
)
from app.services.chat.history_service import ChatHistoryService
from app.services.chat.session_service import ChatSessionService

logger = logging.getLogger(__name__)


class ChatService:
    @classmethod
    async def generate_chat_chunks(
        cls,
        graph,
        input_state: dict,
        config: dict,
        model_name: str,
        thread_id: str,
        background_tasks: BackgroundTasks,
    ) -> AsyncGenerator[ChatCompletionChunk | dict, None]:
        """核心流式响应生成器 - 产出原始 Chunk 对象或状态 dict"""
        full_response = ""
        sources = []
        chunk_id_prefix = f"chatcmpl-{uuid.uuid4()}"

        try:
            async for event in graph.astream_events(input_state, config, version="v1"):
                kind = event["event"]

                # 1. 处理 LLM 流式输出 (Token)
                if kind == "on_chat_model_stream":
                    chunk_data = event["data"]["chunk"]
                    chunk_content = chunk_data.content

                    if chunk_content:
                        full_response += chunk_content
                        yield ChatCompletionChunk(
                            id=chunk_id_prefix,
                            object="chat.completion.chunk",
                            created=int(time.time()),
                            model=model_name,
                            choices=[
                                ChatCompletionChunkChoice(
                                    index=0,
                                    delta=ChatCompletionChunkDelta(content=chunk_content),
                                    finish_reason=None,
                                )
                            ],
                        )

                    if hasattr(chunk_data, "tool_call_chunks") and chunk_data.tool_call_chunks:
                        for tc_chunk in chunk_data.tool_call_chunks:
                            cleaned_tc = convert_tool_call_chunk_to_openai(tc_chunk)
                            yield ChatCompletionChunk(
                                id=chunk_id_prefix,
                                object="chat.completion.chunk",
                                created=int(time.time()),
                                model=model_name,
                                choices=[
                                    ChatCompletionChunkChoice(
                                        index=0,
                                        delta=ChatCompletionChunkDelta(tool_calls=[cleaned_tc]),
                                        finish_reason=None,
                                    )
                                ],
                            )

                # 2. 工具开始调用 - 发送状态指示
                elif kind == "on_tool_start":
                    tool_name = event.get("name", "unknown")
                    logger.debug(f"🔧 [Stream] Tool started: {tool_name}")
                    yield {"status": "tool_calling", "tool": tool_name}

            # 引用提取与善后
            state_snapshot = await graph.aget_state(config)
            if state_snapshot.values:
                final_messages = state_snapshot.values.get("messages", [])
                sources = extract_sources_from_messages(final_messages, from_last_turn=True)

            if sources:
                yield {"sources": sources}

            # 3. 异步更新数据库记录
            async def save_history():
                async with AsyncSessionLocal() as db:
                    state_snapshot = await graph.aget_state(config)
                    final_messages = (
                        state_snapshot.values.get("messages", []) if state_snapshot.values else []
                    )
                    final_response = ""
                    if final_messages:
                        for msg in reversed(final_messages):
                            if isinstance(msg, AIMessage) and msg.content:
                                final_response = msg.content
                                break

                    persistent_content = final_response or full_response
                    if persistent_content:
                        await ChatSessionService.update_assistant_response(
                            db=db, thread_id=thread_id, assistant_message=persistent_content
                        )
                    await ChatHistoryService.save_history_from_messages(
                        db=db, thread_id=thread_id, messages=final_messages
                    )

            background_tasks.add_task(save_history)

        except Exception as e:
            logger.error(f"❌ [ChatService] Stream generator error: {e}", exc_info=True)
            yield ChatCompletionChunk(
                id=f"error-{uuid.uuid4()}",
                model=model_name,
                choices=[
                    ChatCompletionChunkChoice(
                        index=0,
                        delta=ChatCompletionChunkDelta(content=f"\n\n[System Error: {str(e)}]"),
                        finish_reason="stop",
                    )
                ],
            )

    @staticmethod
    async def stream_graph_events(
        graph,
        input_state: dict,
        config: dict,
        model_name: str,
        thread_id: str,
        background_tasks: BackgroundTasks,
    ) -> AsyncGenerator[str, None]:
        """流式响应生成器 - 包装 generate_chat_chunks 并序列化为 SSE 格式"""
        async for chunk in ChatService.generate_chat_chunks(
            graph, input_state, config, model_name, thread_id, background_tasks
        ):
            if isinstance(chunk, ChatCompletionChunk):
                yield f"data: {chunk.model_dump_json()}\n\n"
            else:
                yield f"data: {json.dumps(chunk)}\n\n"

        yield "data: [DONE]\n\n"

    @classmethod
    async def initialize_chat_context(
        cls,
        thread_id: str | None,
        site_id: int,
        user_id: str | None,
        message: str | None = None,
        messages: list[ChatMessage] | None = None,
        model_name: str | None = None,
        temperature: float = 0.7,
    ) -> tuple[ChatOpenAI, dict, dict, int | None]:
        """
        初始化聊天上下文：解析租户、构建 LLM、持久化首条消息并准备 Graph 状态。
        """
        # 1. 确定 thread_id (会话识别)
        # 如果没有显式传 thread_id，尝试将 user 字段映射为线索，否则生成 UUID
        if not thread_id:
            thread_id = (
                user_id if (user_id and len(user_id) > 5) else f"auto-{uuid.uuid4().hex[:12]}"
            )

        from langchain_core.messages import (
            AIMessage,
            HumanMessage,
            SystemMessage,
            ToolMessage,
        )

        # 2. 识别用户输入
        input_message = ""
        context_messages = []

        if messages:
            # 转换 OpenAI 消息到 LangChain 格式
            for m in messages:
                if m.role == "user":
                    context_messages.append(HumanMessage(content=m.content or ""))
                elif m.role == "assistant":
                    context_messages.append(AIMessage(content=m.content or ""))
                elif m.role == "system":
                    context_messages.append(SystemMessage(content=m.content or ""))

            # 取最后一条 user 消息的内容作为 trigger
            for m in reversed(messages):
                if m.role == "user":
                    input_message = m.content or ""
                    break
        else:
            input_message = message or ""
            context_messages = [HumanMessage(content=input_message)]

        # 3. 解析 site_id 和 tenant_id
        tenant_id = None
        async with AsyncSessionLocal() as db:
            site = await crud_site.get(db, id=site_id)
            tenant_id = site.tenant_id if site else None

        # [Important] 设置当前租户上下文
        from app.core.infra.tenant import set_current_tenant

        set_current_tenant(tenant_id)

        # 4. 初始化 LLM
        llm = await llm_manager.get_model(
            tenant_id=tenant_id,
            model_name=model_name,
            temperature=temperature,
        )

        # 5. 持久化 (如果这是该 thread 的新消息)
        async with AsyncSessionLocal() as db:
            try:
                await ChatSessionService.create_or_update(
                    db=db,
                    thread_id=thread_id,
                    site_id=site_id,
                    user_message=input_message,
                    member_id=user_id,
                    tenant_id=tenant_id,
                )
                # 仅保存最后一条用户输入到我们的历史表
                await ChatHistoryService.save_message(
                    db=db, thread_id=thread_id, role="user", content=input_message
                )
            except Exception as e:
                logger.error(f"❌ [ChatService] Failed to persist chat session: {e}")

        # 6. 准备 Graph 初始状态
        initial_state = {
            "messages": context_messages,
            "site_id": site_id,
            "iteration_count": 0,
            "consecutive_empty_count": 0,
        }
        config = {"configurable": {"thread_id": thread_id, "site_id": site_id}}

        return llm, initial_state, config, tenant_id

    @classmethod
    async def process_chat_request(
        cls, request: ChatCompletionRequest, background_tasks: BackgroundTasks
    ) -> ChatCompletionResponse | StreamingResponse:
        """核心聊天处理逻辑 (ReAct Agent)"""
        from app.core.web.exceptions import CatWikiError

        # 确定 site_id (从 filter 或 默认)
        site_id = request.filter.site_id if (request.filter and request.filter.site_id) else 0

        try:
            llm, initial_state, config, tenant_id = await cls.initialize_chat_context(
                thread_id=request.thread_id,
                site_id=site_id,
                user_id=request.user,
                message=request.message,
                messages=request.messages,
                model_name=request.model,
                temperature=request.temperature or 0.7,
            )
            # 更新 request 中的 thread_id 以便后续逻辑一致
            current_thread_id = config["configurable"]["thread_id"]
        except CatWikiError as e:
            # 流式模式下，将业务异常作为 SSE 错误事件返回，前端可在对话气泡中自然展示
            if request.stream:
                # 必须在 except 块内捕获值，因为 Python 3.12 会在块结束后清除 e
                error_detail = e.detail

                async def error_generator():
                    error_chunk = ChatCompletionChunk(
                        id=f"error-{uuid.uuid4()}",
                        model=request.model or "unknown",
                        choices=[
                            ChatCompletionChunkChoice(
                                index=0,
                                delta=ChatCompletionChunkDelta(content=f"⚠️ {error_detail}"),
                                finish_reason="stop",
                            )
                        ],
                    )
                    yield f"data: {error_chunk.model_dump_json()}\n\n"
                    yield "data: [DONE]\n\n"

                return StreamingResponse(error_generator(), media_type="text/event-stream")
            else:
                raise

        try:
            # 7. 执行推理
            if request.stream:

                async def protected_generator():
                    async with get_checkpointer() as cp:
                        graph = create_agent_graph(checkpointer=cp, model=llm)
                        # 调用 SSE 封装层
                        async for sse_chunk in cls.stream_graph_events(
                            graph,
                            initial_state,
                            config,
                            llm.model_name,
                            current_thread_id,
                            background_tasks,
                        ):
                            yield sse_chunk

                return StreamingResponse(
                    protected_generator(),
                    media_type="text/event-stream",
                )
            else:
                # 非流式响应
                async with get_checkpointer() as cp:
                    graph = create_agent_graph(checkpointer=cp, model=llm)
                    result = await graph.ainvoke(initial_state, config)

                    messages = result["messages"]
                    last_message = messages[-1] if messages else AIMessage(content="")
                    content = last_message.content if isinstance(last_message, BaseMessage) else ""

                    # 后台异步保存历史 (已在 site-completions 等场景通过 background_tasks 加速)
                    async def save_history_bg():
                        async with AsyncSessionLocal() as db:
                            await ChatSessionService.update_assistant_response(
                                db=db, thread_id=current_thread_id, assistant_message=content
                            )
                            await ChatHistoryService.save_history_from_messages(
                                db=db, thread_id=current_thread_id, messages=messages
                            )

                    background_tasks.add_task(save_history_bg)

                    return ChatCompletionResponse(
                        id=f"chatcmpl-{uuid.uuid4()}",
                        object="chat.completion",
                        created=int(time.time()),
                        model=llm.model_name,
                        choices=[
                            ChatCompletionChoice(
                                index=0,
                                message=ChatMessage(role="assistant", content=content),
                                finish_reason="stop",
                            )
                        ],
                        usage=None,
                    )

        except Exception as e:
            logger.error(f"❌ [ChatService] Execution Error: {e}", exc_info=True)
            raise e
