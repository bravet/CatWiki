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

负责管理系统级与租户级的动态配置，核心职责：
1. 配置路由：根据 mode (Custom/Platform) 决定配置源。
2. 缓存管理：基于 TTL 的多级缓存策略。
3. 安全审计：敏感信息脱敏与访问日志。
"""

import json
import logging
import time
from typing import Any, Optional

from app.core.common.masking import mask_sensitive_data

logger = logging.getLogger(__name__)


class ConfigurationService:
    """配置服务 (单例模式)

    职责：
    1. 缓存管理：基于 TTL (默认 60s) 的本地内存缓存。
    2. 模式路由：根据 mode 分支，定向到租户或平台配置，无隐式回退。
    3. 安全日志：脱敏处理 API Key，并区分“新鲜加载”与“缓存命中”日志。
    4. 配置身份标识 (Hash/Fingerprint):
       - 系统的物理实例（如向量库连接、Chat 客户端、Reranker 实例等）通过解析后的配置哈希来识别。
       - 哈希组成核心字段：{ "model", "api_key", "base_url", "dimension"(仅向量) }。
       - 当这些核心字段发生变化时，代表该模块的“身份”改变，将触发后端对应实例的重置或重新初始化。
    """

    _instance: Optional["ConfigurationService"] = None

    def __init__(self, cache_ttl: int = 60):
        self._config_cache: dict[str, dict[str, Any]] = {}
        self._last_update_map: dict[str, float] = {}
        self._cache_ttl = cache_ttl

    @classmethod
    def get_instance(cls) -> "ConfigurationService":
        """获取服务单例实例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _mask_config(self, config: dict[str, Any]) -> dict[str, Any]:
        """对敏感字段进行脱敏处理"""
        return mask_sensitive_data(config)

    def _compute_config_hash(self, config: dict[str, Any]) -> str:
        """计算配置指纹 (Identity Hash) - 已统一使用 ConfigResolver"""
        from app.core.infra.config_resolver import ConfigResolver

        return ConfigResolver.compute_config_hash(config)

    def _log_resolved_config(self, section: str, target: str, mode: str, config: dict[str, Any]):
        """打印全量可视化卡片 (仅在数据库加载时触发，内部调试用)"""
        from app.core.common.masking import mask_sensitive_data

        masked = mask_sensitive_data(config)
        model = masked.get("model", "N/A")
        provider = masked.get("provider", "N/A")
        extra_body = masked.get("extra_body")

        try:
            pretty_json = json.dumps(masked, indent=4, ensure_ascii=False)
        except Exception:
            pretty_json = str(masked)

        log_msg = (
            f"\n{'=' * 60}\n"
            f"🔍 [Config Service] -> 🔄 从数据库新鲜加载\n"
            f"   - 模块阶段: {section}\n"
            f"   - 目标对象: {target}\n"
            f"   - 指纹标识: {config.get('_hash', 'N/A')}\n"
            f"   - 命中模式: {mode}\n"
            f"   - 核心模型: {provider} | {model}\n"
            f"   - 扩展参数 (extra_body): {json.dumps(extra_body) if extra_body else 'None'}\n"
            f"   - 完整脱敏快照:\n{pretty_json}\n"
            f"{'=' * 60}"
        )
        logger.info(log_msg)

    def clear_cache(self, tenant_id: int | None = -1):
        """清除缓存

        Args:
            tenant_id:
                - 指定 ID: 清除该租户的缓存
                - None: 清除平台(全局)缓存
                - -1 (默认): 清除所有缓存
        """
        if tenant_id == -1:
            self._config_cache.clear()
            self._last_update_map.clear()
            logger.info("🧹 [ConfigService] 已清空全部配置缓存")
        else:
            cache_key = f"tenant:{tenant_id}" if tenant_id else "platform"
            self._config_cache.pop(cache_key, None)
            self._last_update_map.pop(cache_key, None)
            logger.info(f"🧹 [ConfigService] 已清除 {cache_key} 的配置缓存")

    async def _resolve_config(
        self, section: str, tenant_id: int | None = None, force: bool = False
    ) -> dict[str, Any]:
        """统一配置解析逻辑 (带缓存层)"""
        from app.core.infra.config_resolver import ConfigResolver

        cache_key = f"{section}:tenant:{tenant_id}" if tenant_id else f"{section}:platform"
        now = time.time()

        # 1. 尝试从缓存获取
        if not force:
            last_update = self._last_update_map.get(cache_key, 0)
            if now - last_update < self._cache_ttl and cache_key in self._config_cache:
                return self._config_cache[cache_key]

        # 2. 缓存失效，调用底层 ConfigResolver (逻辑唯一源)
        resolved_config = await ConfigResolver.resolve_section(section, tenant_id=tenant_id)

        # 3. 打印日志并存回缓存
        target_display = f"Tenant {tenant_id}" if tenant_id else "Platform"
        self._log_resolved_config(
            section, target_display, resolved_config.get("_mode", "N/A"), resolved_config
        )

        self._config_cache[cache_key] = resolved_config
        self._last_update_map[cache_key] = now

        return resolved_config

    async def get_chat_config(
        self, tenant_id: int | None = None, force: bool = False
    ) -> dict[str, Any]:
        """获取 Chat 模型配置"""
        return await self._resolve_config("chat", tenant_id, force=force)

    async def get_embedding_config(
        self, tenant_id: int | None = None, force: bool = False
    ) -> dict[str, Any]:
        """获取 Embedding 模型配置"""
        return await self._resolve_config("embedding", tenant_id, force=force)

    async def get_rerank_config(
        self, tenant_id: int | None = None, force: bool = False
    ) -> dict[str, Any]:
        """获取 Rerank 模型配置"""
        return await self._resolve_config("rerank", tenant_id, force=force)

    async def get_vl_config(
        self, tenant_id: int | None = None, force: bool = False
    ) -> dict[str, Any]:
        """获取视觉语言模型配置"""
        return await self._resolve_config("vl", tenant_id, force=force)


# 全局单例
configuration_service = ConfigurationService.get_instance()
