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

import copy
import hashlib
import json
import logging
from typing import Any

from app.core.infra.tenant import temporary_tenant_context
from app.crud.system_config import crud_system_config
from app.db.database import AsyncSessionLocal

logger = logging.getLogger(__name__)

from app.core.infra.config import (
    AI_CHAT_CONFIG_KEY,
    AI_EMBEDDING_CONFIG_KEY,
    AI_RERANK_CONFIG_KEY,
    AI_VL_CONFIG_KEY,
)

SECTION_TO_KEY = {
    "chat": AI_CHAT_CONFIG_KEY,
    "embedding": AI_EMBEDDING_CONFIG_KEY,
    "rerank": AI_RERANK_CONFIG_KEY,
    "vl": AI_VL_CONFIG_KEY,
}


class ConfigResolver:
    """Core configuration resolver logic.

    This class handles the retrieval and resolution of configurations from the database,
    supporting tenant-specific overrides and platform fallbacks.
    It is placed in the core layer to avoid circular dependencies.
    """

    @staticmethod
    def compute_config_hash(config: dict[str, Any]) -> str:
        """Compute Identity Hash for a configuration block."""
        identity_parts = {
            "model": config.get("model"),
            "apiKey": config.get("apiKey"),
            "baseUrl": str(config.get("baseUrl", "")).rstrip("/"),
            "dimension": config.get("dimension"),
            "extra_body": config.get("extra_body"),
        }
        identity_str = json.dumps(identity_parts, sort_keys=True)
        return hashlib.md5(identity_str.encode()).hexdigest()

    @staticmethod
    async def get_raw_db_config(config_key: str, tenant_id: int | None = None) -> dict[str, Any]:
        """Fetch raw configuration from database by key."""
        async with AsyncSessionLocal() as db:
            try:
                with temporary_tenant_context(tenant_id):
                    config = await crud_system_config.get_by_key(
                        db, config_key=config_key, tenant_id=tenant_id
                    )
                return config.config_value if config and config.config_value else {}
            except Exception as e:
                logger.error(
                    f"❌ [ConfigResolver] DB read error (Key: {config_key}, Tenant: {tenant_id}): {e}"
                )
                return {}

    @classmethod
    async def resolve_section(cls, section: str, tenant_id: int | None = None) -> dict[str, Any]:
        """Resolve a specific configuration section (e.g., 'chat', 'embedding')."""
        # 1. Tenant Level
        if tenant_id:
            from app.core.web.exceptions import CatWikiError
            from app.crud.tenant import crud_tenant

            async with AsyncSessionLocal() as db:
                tenant = await crud_tenant.get(db, id=tenant_id)
                if not tenant:
                    raise CatWikiError(f"Tenant {tenant_id} not found")
                allowed_resources = tenant.platform_resources_allowed or []

            # 1.1 Try Specific Module Key
            specific_key = SECTION_TO_KEY.get(section)
            if not specific_key:
                raise CatWikiError(f"Unknown AI section: {section}")

            tenant_section = await cls.get_raw_db_config(specific_key, tenant_id)

            if not tenant_section:
                # 租户没有该模块的配置，明确报错
                raise CatWikiError(f"未配置 '{section}' 模块，请在系统设置中完成 AI 模型配置")

            mode = tenant_section.get("mode")
            if mode == "custom":
                tenant_section.update({"_mode": "custom", "_source": "tenant"})
                tenant_section["_hash"] = cls.compute_config_hash(tenant_section)
                return tenant_section

            if mode == "platform":
                if "models" not in allowed_resources:
                    raise CatWikiError(
                        f"Tenant {tenant_id} attempted to use platform models without 'models' authorization"
                    )
                # Proceed to platform resolution below
            elif mode is None:
                # mode 未设置 — 配置不完整，明确报错
                raise CatWikiError(
                    f"租户 {tenant_id} 的 '{section}' 配置不完整（缺少 mode），请检查 AI 模型配置"
                )
            else:
                raise CatWikiError(f"Invalid config mode for tenant {tenant_id}: {mode}")

        # 2. Platform Level
        specific_key = SECTION_TO_KEY.get(section)
        if not specific_key:
            raise CatWikiError(f"Unknown AI section: {section}")

        platform_section = await cls.get_raw_db_config(specific_key, None)

        if not platform_section:
            from app.core.web.exceptions import CatWikiError

            raise CatWikiError(f"平台未配置 '{section}' 模块，请在系统设置中完成 AI 模型配置")

        platform_section.update({"_mode": "platform", "_source": "platform"})
        platform_section["_hash"] = cls.compute_config_hash(platform_section)
        return platform_section

    @classmethod
    async def log_ai_stack(cls, tenant_id: int | None = None):
        """[✨ 亮点] 打印全量 AI 栈配置快照 (用于 Request 启动时)"""
        try:
            from app.core.common.masking import mask_sensitive_data

            stack = {}
            for section in ["chat", "embedding", "rerank", "vl"]:
                try:
                    conf = await cls.resolve_section(section, tenant_id)
                    stack[section] = mask_sensitive_data(conf)
                except Exception:
                    stack[section] = {"error": "Not configured"}

            target_display = f"Tenant {tenant_id}" if tenant_id else "Platform GLOBAL"

            # 构造精简的摘要表格/列表
            summary_lines = []
            for section, conf in stack.items():
                if "error" in conf:
                    summary_lines.append(f"   [{section:9}] -> ❌ 未配置")
                    continue

                provider = conf.get("provider", "N/A")
                model = conf.get("model", "N/A")
                eb = conf.get("extra_body")
                mode = conf.get("_mode", "platform")
                h = conf.get("_hash", "N/A")[:8]

                eb_str = f" | Extra: {json.dumps(eb)}" if eb else ""
                summary_lines.append(
                    f"   [{section:9}] -> {provider:8} | {model:15} | Mode: {mode:8} | Hash: {h}{eb_str}"
                )

            pretty_stack = "\n".join(summary_lines)

            log_msg = (
                f"\n{'=' * 80}\n"
                f"🧠 [AI Context] -> 🚀 正在初始化推理引擎 (Request Session)\n"
                f"   - 目标范围: {target_display}\n"
                f"{pretty_stack}\n"
                f"{'=' * 80}"
            )
            logger.debug(log_msg)
        except Exception as e:
            logger.warning(f"⚠️ [ConfigResolver] 打印 AI 栈日志失败: {e}")
