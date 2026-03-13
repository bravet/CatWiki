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

"""全局配置服务 (Configuration Service)

负责管理系统级与租户级的动态配置。
现已接入系统统一缓存层，支持多机环境下的配置同步。
"""

import json
import logging
from typing import Any, Optional

from app.core.common.masking import mask_sensitive_data
from app.core.infra.cache import get_cache

logger = logging.getLogger(__name__)


class ConfigurationService:
    """配置服务 (单例模式)

    职责：
    1. 配置获取：作为业务层访问 AI 模型、系统组件配置的统一入口。
    2. 多级路由：根据 mode 分支，定向到租户或平台配置。
    3. 集群缓存：利用系统 BaseCache 实现配置缓存，支持 Redis 下的单点更新、全网生效。
    """

    _instance: Optional["ConfigurationService"] = None

    def __init__(self, cache_ttl: int = 60):
        self._cache_ttl = cache_ttl

    @classmethod
    def get_instance(cls) -> "ConfigurationService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _get_cache_key(self, section: str, tenant_id: int | None) -> str:
        """生成配置专用的缓存键"""
        target = f"tenant:{tenant_id}" if tenant_id else "platform"
        return f"config:{section}:{target}"

    def _log_resolved_config(self, section: str, target: str, config: dict[str, Any]):
        """打印配置加载可视化日志（仅在缓存失效重新加载时触发）"""
        masked = mask_sensitive_data(config)

        try:
            pretty_json = json.dumps(masked, indent=4, ensure_ascii=False)
        except Exception:
            pretty_json = str(masked)

        log_msg = (
            f"\n{'=' * 70}\n"
            f"🔍 [Configuration] -> 🔄 从数据库重新加载配置\n"
            f"   - 模块阶段: {section}\n"
            f"   - 目标对象: {target}\n"
            f"   - 哈希指纹: {config.get('_hash', 'N/A')[:12]}\n"
            f"   - 配置快照:\n{pretty_json}\n"
            f"{'=' * 70}"
        )
        logger.info(log_msg)

    def clear_cache(self, tenant_id: int | None = -1):
        """
        清空配置缓存。
        调用此方法后，系统缓存（内存或 Redis）中相关的配置项将被移除。
        """
        cache = get_cache()
        # 注意：BaseCache.clear 是清空所有，这里我们其实需要根据前缀清理
        # 但目前可以通过 delete 逐个清理重要的 Section，或者如果是租户更新，直接 clear 也是一种策略。
        # 这里为了保持精细度，我们可以调用 delete。
        sections = ["chat", "embedding", "rerank", "vl"]

        async def _do_clear():
            if tenant_id == -1:
                # 如果是全局清理，目前 BaseCache 只提供了 clear（全库清理）
                # 考虑到配置的重要性，直接 clear 是最稳妥的
                await cache.clear()
                logger.info("🧹 已清空系统全部缓存（含配置）")
            else:
                for sec in sections:
                    key = self._get_cache_key(sec, tenant_id)
                    await cache.delete(key)
                logger.info(f"🧹 已清除租户 {tenant_id} 的模型配置缓存")

        # 由于 clear_cache 目前在多处是同步调用（历史遗留），我们起一个 task 或直接执行
        # 建议业务层逐渐迁移到异步调用清理
        import asyncio

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_do_clear())
        except RuntimeError:
            # 兼容非异步环境（如初始化脚本）
            asyncio.run(_do_clear())

    async def _resolve_config(
        self, section: str, tenant_id: int | None = None, force: bool = False
    ) -> dict[str, Any]:
        """统一配置解析逻辑 (接入 BaseCache)"""
        from app.core.infra.config_resolver import ConfigResolver

        cache = get_cache()
        cache_key = self._get_cache_key(section, tenant_id)

        if force:
            await cache.delete(cache_key)

        async def _fetcher():
            # 实际搬砖逻辑
            config = await ConfigResolver.resolve_section(section, tenant_id=tenant_id)
            target_display = f"Tenant {tenant_id}" if tenant_id else "Platform"
            self._log_resolved_config(section, target_display, config)
            return config

        # 使用 get_or_set 极简实现
        return await cache.get_or_set(cache_key, _fetcher, ttl=self._cache_ttl)

    async def get_chat_config(
        self, tenant_id: int | None = None, force: bool = False
    ) -> dict[str, Any]:
        return await self._resolve_config("chat", tenant_id, force=force)

    async def get_embedding_config(
        self, tenant_id: int | None = None, force: bool = False
    ) -> dict[str, Any]:
        return await self._resolve_config("embedding", tenant_id, force=force)

    async def get_rerank_config(
        self, tenant_id: int | None = None, force: bool = False
    ) -> dict[str, Any]:
        return await self._resolve_config("rerank", tenant_id, force=force)

    async def get_vl_config(
        self, tenant_id: int | None = None, force: bool = False
    ) -> dict[str, Any]:
        return await self._resolve_config("vl", tenant_id, force=force)


# 全局单例
configuration_service = ConfigurationService.get_instance()
