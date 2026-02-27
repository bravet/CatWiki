import threading
import time
from typing import Any

from app.core.integration.robot.base import BaseRobotAdapter, RobotInboundEvent, RobotSession


class WeComBufferManager:
    """企业微信流式回复内存缓冲区管理器 (全局单例存储)。"""

    _response_buffer: dict[str, dict[str, Any]] = {}
    _processed_msgids: dict[str, str] = {}  # msgid -> stream_id (去重映射)
    _active_threads: dict[str, str] = {}  # thread_id -> stream_id (正在执行的任务锁)
    _buffer_lock = threading.Lock()

    @classmethod
    def update_buffer(cls, stream_id: str, content: str, is_finish: bool, is_error: bool) -> None:
        with cls._buffer_lock:
            if stream_id not in cls._response_buffer:
                cls._response_buffer[stream_id] = {
                    "content": content if content else "",
                    "finish": is_finish,
                    "timestamp": time.time(),
                }
                return

            payload = cls._response_buffer[stream_id]
            if is_error:
                payload["content"] = (
                    (content + "\n\n服务繁忙，请稍后再试。")
                    if content
                    else "服务繁忙，请稍后再试。"
                )
                payload["finish"] = True
            else:
                # [Optimization] 如果新内容为空但旧内容不为空，且不是报错，则保留旧内容
                # 这解决了 RobotOrchestrator 初始发送 "" 导致企微界面“闪烁”的问题
                if content:
                    payload["content"] = content
                payload["finish"] = is_finish

            payload["timestamp"] = time.time()

            # 如果任务结束，释放线程锁
            if is_finish or is_error:
                # 遍历活跃线程，找到属于此 stream_id 的并删除
                thread_ids_to_release = [
                    tid for tid, sid in cls._active_threads.items() if sid == stream_id
                ]
                for tid in thread_ids_to_release:
                    cls._active_threads.pop(tid, None)

    @classmethod
    def get_buffered_response(cls, stream_id: str) -> dict[str, Any] | None:
        with cls._buffer_lock:
            return cls._response_buffer.get(stream_id)

    @classmethod
    def get_stream_id_by_msgid(cls, msgid: str) -> str | None:
        """根据企微消息 ID 获取已生成的流 ID (用于去重)"""
        with cls._buffer_lock:
            return cls._processed_msgids.get(msgid)

    @classmethod
    def register_msgid(cls, msgid: str, stream_id: str) -> None:
        """记录消息 ID 与流 ID 的对应关系"""
        with cls._buffer_lock:
            cls._processed_msgids[msgid] = stream_id

    @classmethod
    def lock_thread(cls, thread_id: str, stream_id: str) -> bool:
        """锁定线程，防止同一会话并发 AI 任务"""
        with cls._buffer_lock:
            if thread_id in cls._active_threads:
                return False
            cls._active_threads[thread_id] = stream_id
            return True

    @classmethod
    def get_stream_id_by_thread(cls, thread_id: str) -> str | None:
        """获取当前正在执行的线程对应的流 ID"""
        with cls._buffer_lock:
            return cls._active_threads.get(thread_id)

    @classmethod
    def cleanup_buffer(cls, expiry_seconds: int = 300) -> int:
        now = time.time()
        count = 0
        with cls._buffer_lock:
            # 1. 清理响应缓存
            keys_to_remove = [
                sid
                for sid, task in cls._response_buffer.items()
                if now - task.get("timestamp", 0) > expiry_seconds
            ]
            for k in keys_to_remove:
                cls._response_buffer.pop(k, None)
                count += 1

            # 2. 清理过期的线程锁 (容错处理)
            # 如果一个任务超过 600 秒没有更新，强制释放锁以防死锁
            threads_to_expire = [
                tid
                for tid, sid in cls._active_threads.items()
                if (sid not in cls._response_buffer)  # 对应的 buffer 已经被上面清掉了
            ]
            for tid in threads_to_expire:
                cls._active_threads.pop(tid, None)

            # 3. 清理去重缓存 (msgid)
            msgids_to_remove = [
                mid for mid, sid in cls._processed_msgids.items() if sid not in cls._response_buffer
            ]
            for mid in msgids_to_remove:
                cls._processed_msgids.pop(mid, None)

        return count


class WeComAdapter(BaseRobotAdapter):
    """企业微信智能机器人适配器。"""

    def get_provider_name(self) -> str:
        return "企业微信智能机器人"

    def get_provider_id(self) -> str:
        return "wecom_smart"

    def get_sync_interval(self) -> float:
        """企业微信采用 Pull 模式，由于是局部内存更新，0.5s 可以提供更连贯的轮询响应。"""
        return 0.5

    def parse_inbound_text_event(self, data: Any, site_id: int) -> RobotInboundEvent | None:
        """企微验证和解密在 Endpoint 中完成，这里暂不使用。"""
        raise NotImplementedError("企微 Webhook 暂时由 Endpoint 直接解析成 RobotInboundEvent")

    async def reply(
        self,
        session: RobotSession,
        content: str,
        is_finish: bool = False,
        is_error: bool = False,
    ) -> None:
        """更新企微流式缓冲区。"""
        stream_id = session.context_id
        if not stream_id:
            return

        WeComBufferManager.update_buffer(stream_id, content, is_finish, is_error)
