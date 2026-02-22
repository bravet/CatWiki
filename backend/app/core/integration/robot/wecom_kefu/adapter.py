# Copyright 2026 CatWiki Authors

import logging
from app.core.integration.robot.base import RobotSession, BaseRobotAdapter
from .service import WeComKefuService

logger = logging.getLogger(__name__)


class WeComKefuAdapter(BaseRobotAdapter):
    """企业微信客服适配器。"""

    def get_provider_name(self) -> str:
        return "企业微信客服"

    async def reply(
        self,
        session: RobotSession,
        content: str,
        is_finish: bool = False,
        is_error: bool = False,
    ) -> None:
        """
        客服消息回复逻辑。
        微信客服回复通过 API 发送，而非 Webhook 响应。
        """
        if not is_finish and not is_error:
            # 微信客服通常不支持流式，我们只在完成或错误时发送完整回复
            return

        # 获取配置
        config = session.config
        if not config or not isinstance(config, dict):
            logger.error("WeComKefuAdapter: 缺失配置信息")
            return

        corp_id = config.get("corpId")
        secret = config.get("secret")

        # 从会话中获取原始事件信息
        inbound_event = session.event
        open_kfid = inbound_event.metadata.get("open_kfid")
        external_userid = inbound_event.from_user

        if not open_kfid or not external_userid:
            logger.error("WeComKefuAdapter: 缺失 open_kfid 或 external_userid")
            return

        # 发送客服消息
        await WeComKefuService.send_message(
            corp_id=corp_id,
            secret=secret,
            open_kfid=open_kfid,
            external_userid=external_userid,
            content=content,
        )
