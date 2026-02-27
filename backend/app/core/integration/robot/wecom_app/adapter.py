# Copyright 2026 CatWiki Authors

import logging
from typing import Any
from app.core.integration.robot.base import RobotSession, BaseRobotAdapter, RobotInboundEvent

logger = logging.getLogger(__name__)


class WeComAppAdapter(BaseRobotAdapter):
    """企业微信应用(机器人)适配器。"""

    def get_provider_name(self) -> str:
        return "企业微信机器人"

    def get_provider_id(self) -> str:
        return "wecom_app"

    def parse_inbound_text_event(self, data: Any, site_id: int) -> RobotInboundEvent | None:
        """应用消息暂时由 Service 直接解析。"""
        raise NotImplementedError("企业微信应用消息暂时由 Service 直接解析")

    def is_streaming_supported(self, session: RobotSession | None = None) -> bool:
        """不支持流式"""
        return False

    async def reply(
        self,
        session: RobotSession,
        content: str,
        is_finish: bool = False,
        is_error: bool = False,
    ) -> None:
        """
        通过企业微信 API 发送消息。
        应用消息通常不支持原生流式，我们在完成或错误时发送。
        """
        if not is_finish and not is_error:
            return

        # 获取配置
        config = session.config
        if not config or not isinstance(config, dict):
            logger.error("WeComAppAdapter: 缺失配置信息")
            return

        corp_id = config.get("corp_id")
        secret = config.get("secret")
        agent_id = config.get("agent_id")

        # 从会话中获取用户信息
        external_userid = session.event.from_user

        if not corp_id or not secret or not agent_id:
            logger.error("WeComAppAdapter: 配置不完整 (corp_id/secret/agent_id)")
            return

        # 发送应用消息
        from .service import WeComAppService

        await WeComAppService.send_message(
            corp_id=corp_id,
            secret=secret,
            agent_id=agent_id,
            to_user=external_userid,
            content=content,
        )
