import logging
import uuid
from typing import Any

from app.core.integration.robot.base import BaseRobotAdapter, RobotInboundEvent, RobotSession
from app.core.integration.robot.connections.wecom_longconn import WeComSmartLongConnRegistry

logger = logging.getLogger(__name__)


class WeComSmartAdapter(BaseRobotAdapter):
    """企业微信智能机器人适配器 (长连接模式)。"""

    def get_provider_name(self) -> str:
        return "企业微信智能机器人"

    def get_provider_id(self) -> str:
        return "wecom_smart"

    def get_sync_interval(self) -> float:
        """企微智能机器人长连接推送通常由 AI 生成流式段落，建议 0.8s 左右平衡体验。"""
        return 0.8

    def parse_inbound_text_event(self, data: Any, site_id: int) -> RobotInboundEvent | None:
        """解析企微智能机器人长连接入站消息 aibot_msg_callback。"""
        headers = data.get("headers", {})
        body = data.get("body", {})

        msg_type = body.get("msgtype")
        if msg_type != "text":
            return None

        # 在长连接中，req_id 是核心，消息的 ID 则在 body.msgid
        req_id = headers.get("req_id")
        text = (body.get("text", {}).get("content", "")).strip()
        from_info = body.get("from", {})
        from_user = from_info.get("alias") or from_info.get("userid", "anonymous")
        chat_id = body.get("chatid")

        if not text:
            return None

        return RobotInboundEvent(
            site_id=site_id,
            message_id=req_id,  # 我们用 req_id 作为逻辑 ID 以便回传给 headers
            from_user=from_user,
            content=text,
            chat_id=chat_id,
            raw_data=data,
            extra={
                "wecom_msgid": body.get("msgid"),  # 原始 msgid
            },
        )

    async def reply(
        self,
        session: RobotSession,
        content: str,
        is_finish: bool = False,
        is_error: bool = False,
    ) -> None:
        """通过企微智能机器人长连接发送/刷新流式消息。"""
        # 注意：WeCom 长连接依赖于 req_id (保存在 session.event.message_id)
        req_id = session.event.message_id
        if not req_id:
            logger.warning(
                "企微智能机器人回复失败: 缺少 req_id (site_id=%s)", session.event.site_id
            )
            return

        # 企微智能机器人长连接需要生成一个 stream_id，如果 session.context_id 没定义则新生成一个
        if not session.context_id:
            session.context_id = str(uuid.uuid4())

        payload: dict[str, Any] = {
            "cmd": "aibot_respond_msg",
            "headers": {"req_id": req_id},
            "body": {
                "msgtype": "stream",
                "stream": {
                    "id": session.context_id,
                    "finish": is_finish,
                    "content": content
                    if not is_error
                    else (content + "\n\n(服务暂时不可用，请稍后再试)"),
                },
            },
        }

        success = await WeComSmartLongConnRegistry.send(session.event.site_id, payload)
        if not success:
            logger.warning(
                "企微智能机器人长连接回复指令发送失败: site_id=%s req_id=%s",
                session.event.site_id,
                req_id,
            )
