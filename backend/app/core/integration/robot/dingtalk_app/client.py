import asyncio
import json
import logging
import time
import uuid
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class DingTalkClient:
    """钉钉消息发送封装。"""

    DINGTALK_BASE_URL = "https://api.dingtalk.com"

    def __init__(self) -> None:
        self._token_cache: dict[str, dict[str, float | str]] = {}
        self._token_lock = asyncio.Lock()
        # 持久化异步客户端，复用连接池
        self._http_client = httpx.AsyncClient(
            timeout=30.0, limits=httpx.Limits(max_connections=100, max_keepalive_connections=50)
        )

    async def close(self) -> None:
        """释放底层 HTTP 客户端资源。"""
        await self._http_client.aclose()

    async def create_streaming_card(
        self,
        *,
        client_id: str,
        client_secret: str,
        template_id: str,
        event: Any,
        title: str,
    ) -> str:
        """
        初始化创建一张专门用于打字机效果流式输出的互动卡片，并返回 card_instance_id 用于后续 update 追刷
        """
        access_token = await self._get_access_token(
            client_id=client_id, client_secret=client_secret
        )
        headers = {
            "Content-Type": "application/json",
            "Accept": "*/*",
            "x-acs-dingtalk-access-token": access_token,
        }
        card_instance_id = f"catwiki_stream_{uuid.uuid4().hex}"

        # 初始卡片内容使用数值状态码：1-处理中，2-输出中，3-完成
        card_param_map = {
            "content": "",
            "markdown": "",
            "text": "",
            "msgContent": "",
            "msgTitle": title,
            "flowStatus": "2",
            "sys_full_json_obj": json.dumps(
                {
                    "order": [
                        "msgTitle",
                        "content",
                        "msgContent",
                        "staticMsgContent",
                    ]
                },
                ensure_ascii=False,
            ),
            "title": title,
        }
        json_body = self._build_create_and_deliver_body(
            client_id=client_id,
            template_id=template_id,
            card_instance_id=card_instance_id,
            card_param_map=card_param_map,
            event=event,
            title=title,
        )

        await self._request_openapi(
            method="POST",
            url=f"{self.DINGTALK_BASE_URL}/v1.0/card/instances/createAndDeliver",
            headers=headers,
            json_body=json_body,
            action="创建流式卡片容器",
        )
        logger.info(
            "钉钉流式卡片创建成功: template_id=%s out_track_id=%s", template_id, card_instance_id
        )
        return card_instance_id

    async def update_streaming_card(
        self,
        *,
        client_id: str,
        client_secret: str,
        card_instance_id: str,
        content: str | dict[str, str],
        key: str = "content",
        is_full: bool = True,
        is_finalize: bool = False,
        is_error: bool = False,
    ) -> None:
        """
        调用钉钉卡片专用 /v1.0/card/streaming 接口局部刷数据
        """
        access_token = await self._get_access_token(
            client_id=client_id, client_secret=client_secret
        )
        headers = {
            "Content-Type": "application/json",
            "Accept": "*/*",
            "x-acs-dingtalk-access-token": access_token,
        }

        # 支持传入字典，如果传的不是字典，为了兼容转为单键字典
        content_dict = content if isinstance(content, dict) else {key: content}

        for k, v in content_dict.items():
            json_body = {
                "outTrackId": card_instance_id,
                "key": k,
                "content": v,
                "isFull": is_full,
                "isFinalize": is_finalize,
                "isError": is_error,
                "guid": str(uuid.uuid4()),
            }

            await self._request_openapi(
                method="PUT",
                url=f"{self.DINGTALK_BASE_URL}/v1.0/card/streaming",
                headers=headers,
                json_body=json_body,
                action=f"更新流式模板卡片(key={k})",
            )

        logger.debug(
            "钉钉流式卡片更新成功: out_track_id=%s, keys=%s, finalized=%s",
            card_instance_id,
            list(content_dict.keys()),
            is_finalize,
        )

    async def update_card_instance(
        self,
        *,
        client_id: str,
        client_secret: str,
        card_instance_id: str,
        card_param_map: dict[str, Any],
    ) -> None:
        """更新卡片实例参数（例如 flowStatus 收尾置为完成）。"""
        access_token = await self._get_access_token(
            client_id=client_id, client_secret=client_secret
        )
        headers = {
            "Content-Type": "application/json",
            "Accept": "*/*",
            "x-acs-dingtalk-access-token": access_token,
        }
        json_body = {
            "outTrackId": card_instance_id,
            "cardData": {
                "cardParamMap": {k: str(v) for k, v in card_param_map.items()},
            },
        }
        await self._request_openapi(
            method="PUT",
            url=f"{self.DINGTALK_BASE_URL}/v1.0/card/instances",
            headers=headers,
            json_body=json_body,
            action="更新卡片实例",
        )

    @staticmethod
    def _build_create_and_deliver_body(
        *,
        client_id: str,
        template_id: str,
        card_instance_id: str,
        card_param_map: dict[str, str],
        event: Any,
        title: str,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "cardTemplateId": template_id,
            "outTrackId": card_instance_id,
            "cardData": {"cardParamMap": card_param_map},
            "callbackType": "STREAM",
            "userIdType": 1,
        }
        if event.sender_staff_id:
            body["userId"] = event.sender_staff_id

        im_space_model = {
            "supportForward": True,
            "lastMessageI18n": {"ZH_CN": title},
            "searchSupport": {"searchIcon": "", "searchDesc": "来自 CatWiki 的内容回复"},
        }

        if event.conversation_type == "2" and event.conversation_id:
            body["openSpaceId"] = f"dtv1.card//IM_GROUP.{event.conversation_id}"
            group_deliver: dict[str, Any] = {"robotCode": client_id}
            if event.sender_staff_id:
                group_deliver["atUserIds"] = {
                    event.sender_staff_id: event.sender_nick or event.sender_staff_id
                }
            body["imGroupOpenDeliverModel"] = group_deliver
            body["imGroupOpenSpaceModel"] = im_space_model
        elif event.sender_staff_id:
            body["openSpaceId"] = f"dtv1.card//im_robot.{event.sender_staff_id}"
            body["imRobotOpenDeliverModel"] = {"spaceType": "IM_ROBOT", "robotCode": client_id}
            body["imRobotOpenSpaceModel"] = im_space_model
        else:
            raise RuntimeError("钉钉模板卡片投放失败: 缺少会话标识")

        return body

    async def _request_openapi(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        json_body: dict[str, Any],
        action: str,
    ) -> dict[str, Any]:
        """通用的 OpenAPI 请求方法"""
        method_upper = method.upper()
        try:
            if method_upper == "POST":
                resp = await self._http_client.post(url, headers=headers, json=json_body)
            elif method_upper == "PUT":
                resp = await self._http_client.put(url, headers=headers, json=json_body)
            else:
                raise RuntimeError(f"不支持的请求方法: {method}")
            resp_text = resp.text
        except Exception as e:
            logger.error(f"钉钉 {action} 网络异常: {e}")
            raise RuntimeError(f"{action} 网络连接失败: {e}") from e

        if resp.status_code >= 400:
            raise RuntimeError(
                f"{action} HTTP 异常: status={resp.status_code}, body={resp_text[:500]}"
            )

        if not resp_text:
            return {}

        try:
            data = resp.json()
        except Exception:
            return {"raw": resp_text[:500]}

        if isinstance(data, dict):
            code = data.get("code")
            errcode = data.get("errcode")
            success = data.get("success")
            if code not in (None, 0, "0"):
                raise RuntimeError(
                    f"{action}失败: code={code} msg={data.get('message') or data.get('msg')}"
                )
            if errcode not in (None, 0, "0"):
                raise RuntimeError(
                    f"{action}失败: errcode={errcode} errmsg={data.get('errmsg') or data.get('message')}"
                )
            if success is False:
                raise RuntimeError(
                    f"{action}失败: message={data.get('message') or data.get('msg')}"
                )
        return data if isinstance(data, dict) else {"raw": str(data)}

    async def _get_access_token(self, *, client_id: str, client_secret: str) -> str:
        now = time.time()
        cache_key = f"{client_id}:{client_secret}"
        cached = self._token_cache.get(cache_key)
        if cached:
            token = cached.get("token")
            expires_at = float(cached.get("expires_at", 0))
            if isinstance(token, str) and token and expires_at - now > 60:
                return token

        async with self._token_lock:
            now = time.time()
            cached = self._token_cache.get(cache_key)
            if cached:
                token = cached.get("token")
                expires_at = float(cached.get("expires_at", 0))
                if isinstance(token, str) and token and expires_at - now > 60:
                    return token

            url = f"{self.DINGTALK_BASE_URL}/v1.0/oauth2/accessToken"
            payload = {"appKey": client_id, "appSecret": client_secret}
            resp = await self._http_client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()

            token = data.get("accessToken")
            if not token:
                raise RuntimeError(f"钉钉获取 access_token 失败: {str(data)[:300]}")
            expire_seconds = int(data.get("expireIn", 7200) or 7200)
            self._token_cache[cache_key] = {
                "token": token,
                "expires_at": now + max(expire_seconds, 120),
            }
            return token
