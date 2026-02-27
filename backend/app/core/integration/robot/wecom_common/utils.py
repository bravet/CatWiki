# Copyright 2026 CatWiki Authors
import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class WeComTokenManager:
    """企业微信 Access Token 管理器 (带缓存)。"""

    _cache: dict[str, dict[str, Any]] = {}

    @classmethod
    async def get_access_token(cls, corp_id: str, secret: str) -> str:
        """获取微信 access_token (带缓存)"""
        cache_key = f"{corp_id}:{secret}"
        now = time.time()

        if cache_key in cls._cache:
            cache = cls._cache[cache_key]
            if now < cache["expires_at"]:
                return cache["token"]

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://qyapi.weixin.qq.com/cgi-bin/gettoken",
                params={"corpid": corp_id, "corpsecret": secret},
                timeout=10,
            )
            data = resp.json()
            if data.get("errcode") != 0:
                logger.error(f"获取企业微信 Access Token 失败: {data}")
                raise ValueError(f"获取 Access Token 失败: {data.get('errmsg')}")

            token = data["access_token"]
            # 提前 5 分钟过期
            expires_at = now + data["expires_in"] - 300
            cls._cache[cache_key] = {"token": token, "expires_at": expires_at}
            return token
