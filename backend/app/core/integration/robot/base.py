import abc
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel


class BaseRobotConfig(BaseModel):
    """跨平台通用适配器配置基类。"""

    pass


@dataclass
class RobotInboundEvent:
    """标准化的平台输入事件。"""

    site_id: int
    message_id: str | None
    from_user: str
    content: str
    chat_id: str | None = None
    raw_data: Any = None
    # 扩展字段（如钉钉的 session_webhook, 企微的 stream_id 等）
    extra: dict[str, Any] = None


@dataclass
class RobotSession:
    """机器人回复会话状态封装。"""

    event: RobotInboundEvent
    # 平台特定的会话上下文（如飞书的 message_id, 钉钉的 card_instance_id）
    context_id: str | None = None
    # 平台特定的配置
    config: BaseRobotConfig | None = None


class BaseRobotAdapter(abc.ABC):
    """机器人平台适配器基类。"""

    @abc.abstractmethod
    def get_provider_name(self) -> str:
        """模型显示名称 (如：企业微信)。"""
        pass

    @abc.abstractmethod
    def get_provider_id(self) -> str:
        """模型唯一标识 (如：wecom)。"""
        pass

    @abc.abstractmethod
    def parse_inbound_text_event(self, data: Any, site_id: int) -> RobotInboundEvent | None:
        """
        将平台原始回调对象直接解析为标准化的 RobotInboundEvent。
        :param data: 平台 SDK 传来的原始字典或对象
        :param site_id: 所属站点 ID
        """
        pass

    @abc.abstractmethod
    async def reply(
        self,
        session: RobotSession,
        content: str,
        is_finish: bool = False,
        is_error: bool = False,
    ) -> None:
        """
        向平台回复/更新消息。
        :param session: 会话模型
        :param content: 回复内容（流式场景下可能为全量或增量，取决于实现）
        :param is_finish: 是否回答结束
        :param is_error: 是否发生错误
        """
        pass

    def get_sync_interval(self) -> float:
        """获取平台建议的流式同步间隔（秒）。默认 0.6s。"""
        return 0.6

    def is_streaming_supported(self, session: RobotSession | None = None) -> bool:
        """
        判断当前机器人平台是否支持流式推送。
        默认支持流式。对于不支持的原生 API 推送（如企微内部应用/企微客服），子类可重写为 False。
        在为 False 时，Orchestrator 将使用 `stream: False` 一次性请求大模型以获得更快的回报。
        """
        return True

    async def close(self) -> None:
        """释放资源（可选）。"""
        pass


class MessageDeduplicator:
    """机器人消息去重工具类，防止同一消息被多次处理。"""

    def __init__(self, ttl: int = 600, max_size: int = 2000) -> None:
        import threading
        from collections import OrderedDict

        self._ttl = ttl
        self._max_size = max_size
        self._cache: OrderedDict[str, float] = OrderedDict()
        self._lock = threading.Lock()

    def is_duplicate(self, message_id: str) -> bool:
        """判断消息是否重复。如果第一次见则记录并返回 False，否则返回 True。"""
        import time

        if not message_id:
            return False

        now = time.time()
        with self._lock:
            # 1. 清理过期数据
            expire_before = now - self._ttl
            while self._cache:
                first_key = next(iter(self._cache))
                if self._cache[first_key] >= expire_before:
                    break
                self._cache.popitem(last=False)

            # 2. 查重
            if message_id in self._cache:
                return True

            # 3. 记录新消息
            self._cache[message_id] = now
            self._cache.move_to_end(message_id)

            # 4. 容量控制
            if len(self._cache) > self._max_size:
                self._cache.popitem(last=False)

            return False
