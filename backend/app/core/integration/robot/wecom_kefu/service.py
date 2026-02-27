import json
import logging
import threading
import time
from collections import OrderedDict
from typing import Any, Optional

import httpx
import xml.etree.cElementTree as ET

from app.core.integration.robot.base import MessageDeduplicator, RobotInboundEvent, RobotSession
from app.core.integration.robot.wecom_common.utils import WeComTokenManager
from app.models.site import Site
from app.services.robot import RobotOrchestrator


class WeComKefuService:
    """企业微信客服业务逻辑。"""

    _token_manager = WeComTokenManager()
    _deduplicator = MessageDeduplicator()

    @classmethod
    async def send_message(
        cls, corp_id: str, secret: str, open_kfid: str, external_userid: str, content: str
    ) -> None:
        """调用微信客服 API 发送消息"""
        try:
            token = await cls._token_manager.get_access_token(corp_id, secret)
            async with httpx.AsyncClient() as client:
                body = {
                    "touser": external_userid,
                    "open_kfid": open_kfid,
                    "msgtype": "text",
                    "text": {"content": content},
                }
                resp = await client.post(
                    "https://qyapi.weixin.qq.com/cgi-bin/kf/send_msg",
                    params={"access_token": token},
                    json=body,
                    timeout=10,
                )
                data = resp.json()
                if data.get("errcode") != 0:
                    logger.error(f"发送微信客服消息失败: {data}")
        except Exception as e:
            logger.error(f"发送微信客服消息发生异常: {e}")

    @classmethod
    def verify_url(
        cls, crypt: Any, msg_signature: str, timestamp: str, nonce: str, echostr: str
    ) -> str:
        """验证企业微信客服回调 URL"""
        ret, decrypted_echostr = crypt.VerifyURL(msg_signature, timestamp, nonce, echostr)
        if ret != 0:
            logger.error(f"企业微信客服回调 URL 验证失败: 错误码={ret}")
            raise ValueError(f"验证失败: {ret}")
        return decrypted_echostr

    @classmethod
    async def process_webhook(
        cls,
        site: Site,
        crypt: Any,
        post_data: bytes,
        msg_signature: str,
        timestamp: str,
        nonce: str,
        background_tasks: Any,
    ) -> str:
        """处理企业微信客服 Webhook 消息"""
        ret, msg_body = crypt.DecryptMsg(post_data, msg_signature, timestamp, nonce)
        if ret != 0:
            logger.error(f"企业微信客服消息解密失败: 错误码={ret}")
            raise ValueError(f"解密失败: {ret}")

        try:
            xml_tree = ET.fromstring(msg_body)
            msg_type = xml_tree.find("MsgType").text
            msg_id = xml_tree.find("MsgId").text if xml_tree.find("MsgId") is not None else None

            # 1. 去重逻辑
            if msg_id and cls._deduplicator.is_duplicate(msg_id):
                logger.debug("微信客服忽略重复消息: msg_id=%s", msg_id)
                return "success"

            # 微信客服消息事件类型
            if msg_type == "event":
                event = xml_tree.find("Event").text
                if event == "kf_msg_or_event":
                    token = xml_tree.find("Token").text
                    # 需要调用同步接口拉取消息，但通常简化处理
                    # 这里如果是回调，通常会有具体的 MsgType
                    pass

            # 具体的客服消息内容
            # 注意：微信客服如果是通过回调接收，通常是带 Token 的通知，需要去拉取
            # 但如果是“接收客服消息”配置了回调，则会直接推送到这里。
            # 参考：https://developer.work.weixin.qq.com/document/path/94670

            # 这里我们处理最常见的文本消息
            from_user = (
                xml_tree.find("ExternalUserID").text
                if xml_tree.find("ExternalUserID") is not None
                else None
            )
            open_kfid = (
                xml_tree.find("OpenKFID").text if xml_tree.find("OpenKFID") is not None else None
            )
            content_node = xml_tree.find("Text/Content")
            content = content_node.text if content_node is not None else ""

            if from_user and open_kfid and content:
                await cls.handle_text_message(
                    site=site,
                    from_user=from_user,
                    open_kfid=open_kfid,
                    content=content,
                    background_tasks=background_tasks,
                )

        except Exception as e:
            logger.error(f"解析企业微信客服 XML 消息失败: {e}")
            # 即使解析失败也返回 success 避免微信重试

        return "success"

    @classmethod
    async def handle_text_message(
        cls, site: Site, from_user: str, open_kfid: str, content: str, background_tasks: Any
    ) -> None:
        """处理文本消息：启动编排"""
        bot_config = site.bot_config.get("wecom_kefu", {})

        inbound_event = RobotInboundEvent(
            site_id=site.id,
            message_id=None,
            from_user=from_user,
            content=content,
            extra={"open_kfid": open_kfid},
        )

        from app.core.integration.robot.factory import RobotFactory

        adapter = RobotFactory.get_adapter("wecom_kefu")
        session = RobotSession(
            event=inbound_event,
            context_id=f"kf_{from_user}",
            config=bot_config,
        )

        background_tasks.add_task(
            RobotOrchestrator.orchestrate_reply,
            adapter=adapter,
            session=session,
            background_tasks=background_tasks,
        )
