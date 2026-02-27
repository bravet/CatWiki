# Copyright 2026 CatWiki Authors

import logging
import threading
import time
from collections import OrderedDict
from typing import Any

import httpx
import xml.etree.cElementTree as ET

from app.core.integration.robot.base import MessageDeduplicator, RobotInboundEvent, RobotSession
from app.core.integration.robot.wecom_common.utils import WeComTokenManager
from app.models.site import Site
from app.services.robot import RobotOrchestrator

logger = logging.getLogger(__name__)


class WeComAppService:
    """企业微信应用(机器人)业务逻辑。"""

    _token_manager = WeComTokenManager()
    _deduplicator = MessageDeduplicator()

    @classmethod
    async def send_message(
        cls, corp_id: str, secret: str, agent_id: str | int, to_user: str, content: str
    ) -> None:
        """调用企业微信 API 发送应用消息 (支持多租户配置)"""
        try:
            token = await cls._token_manager.get_access_token(corp_id, secret)
            async with httpx.AsyncClient() as client:
                body = {
                    "touser": to_user,
                    "msgtype": "text",
                    "agentid": agent_id,
                    "text": {"content": content},
                    "safe": 0,
                    "enable_id_trans": 0,
                    "enable_duplicate_check": 0,
                }
                resp = await client.post(
                    "https://qyapi.weixin.qq.com/cgi-bin/message/send",
                    params={"access_token": token},
                    json=body,
                    timeout=10,
                )
                data = resp.json()
                if data.get("errcode") != 0:
                    logger.error(f"发送企业微信应用消息失败: {data}")
        except Exception as e:
            logger.error(f"发送企业微信应用消息发生异常: {e}")

    @classmethod
    def verify_url(
        cls, crypt: Any, msg_signature: str, timestamp: str, nonce: str, echostr: str
    ) -> str:
        """验证企业微信应用回调 URL"""
        ret, decrypted_echostr = crypt.VerifyURL(msg_signature, timestamp, nonce, echostr)
        if ret != 0:
            logger.error(f"企业微信应用回调 URL 验证失败: 错误码={ret}")
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
        """处理企业微信应用 Webhook 消息 (XML 协议)"""
        ret, msg_body = crypt.DecryptMsg(post_data, msg_signature, timestamp, nonce)
        if ret != 0:
            logger.error(f"企业微信应用消息解密失败: 错误码={ret}")
            raise ValueError(f"解密失败: {ret}")

        try:
            xml_tree = ET.fromstring(msg_body)
            msg_type = xml_tree.find("MsgType").text
            msg_id = xml_tree.find("MsgId").text if xml_tree.find("MsgId") is not None else None
            from_user = (
                xml_tree.find("FromUserName").text
                if xml_tree.find("FromUserName") is not None
                else None
            )
            agent_id = (
                xml_tree.find("AgentID").text if xml_tree.find("AgentID") is not None else None
            )

            # 1. 去重逻辑
            if msg_id and cls._deduplicator.is_duplicate(msg_id):
                logger.debug("企业微信应用忽略重复消息: msg_id=%s", msg_id)
                return "success"

            # 2. 处理文本消息
            if msg_type == "text":
                content_node = xml_tree.find("Content")
                content = content_node.text if content_node is not None else ""

                if from_user and content:
                    await cls.handle_text_message(
                        site=site,
                        from_user=from_user,
                        agent_id=agent_id,
                        content=content,
                        background_tasks=background_tasks,
                    )

        except Exception as e:
            logger.error(f"解析企业微信应用 XML 消息失败: {e}")

        return "success"

    @classmethod
    async def handle_text_message(
        cls, site: Site, from_user: str, agent_id: str, content: str, background_tasks: Any
    ) -> None:
        """启动统一编排逻辑"""
        bot_config = site.bot_config.get("wecom_app", {})

        inbound_event = RobotInboundEvent(
            site_id=site.id,
            message_id=None,
            from_user=from_user,
            content=content,
            extra={"agent_id": agent_id},
        )

        from app.core.integration.robot.factory import RobotFactory

        adapter = RobotFactory.get_adapter("wecom_app")
        session = RobotSession(
            event=inbound_event,
            context_id=f"app_{from_user}",
            config=bot_config,
        )

        background_tasks.add_task(
            RobotOrchestrator.orchestrate_reply,
            adapter=adapter,
            session=session,
            background_tasks=background_tasks,
        )
