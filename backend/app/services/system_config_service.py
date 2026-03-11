import asyncio
import copy
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.common.masking import mask_sensitive_data
from app.core.infra.config import (
    AI_CHAT_CONFIG_KEY,
    AI_EMBEDDING_CONFIG_KEY,
    AI_RERANK_CONFIG_KEY,
    AI_VL_CONFIG_KEY,
    DOC_PROCESSOR_CONFIG_KEY,
)
from app.core.infra.tenant import get_current_tenant, temporary_tenant_context
from app.core.web.exceptions import BadRequestException
from app.crud.system_config import crud_system_config
from app.services.config.configuration_service import configuration_service

logger = logging.getLogger(__name__)

MODEL_TYPES = ["chat", "embedding", "rerank", "vl"]


class SystemConfigService:
    @staticmethod
    def resolve_target_tenant_id(scope: str) -> int | None:
        """根据 scope 确定目标租户 ID"""
        if scope == "platform":
            return None
        return get_current_tenant()

    @staticmethod
    def _create_openai_client(api_key: str, base_url: str, timeout: float = 10.0):
        from openai import AsyncOpenAI

        return AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=timeout)

    @staticmethod
    async def get_ai_config(db: AsyncSession, target_tenant_id: int | None) -> dict | None:
        """获取 AI 模型配置"""
        with temporary_tenant_context(target_tenant_id):
            configs = []
            for key in [
                AI_CHAT_CONFIG_KEY,
                AI_EMBEDDING_CONFIG_KEY,
                AI_RERANK_CONFIG_KEY,
                AI_VL_CONFIG_KEY,
            ]:
                config = await crud_system_config.get_by_key(
                    db, config_key=key, tenant_id=target_tenant_id
                )
                if config:
                    configs.append(config)

            if not configs:
                return None

            result = {}
            for config in configs:
                # 获取展示名称 (chat/embedding/...)
                type_name = config.config_key.replace("ai_", "").replace("_config", "")
                val = copy.deepcopy(config.config_value)
                # 敏感字段掩补
                val = mask_sensitive_data(val)
                result[type_name] = val

            return result

    @staticmethod
    async def update_ai_config(
        db: AsyncSession, target_tenant_id: int | None, update_data: Any
    ) -> dict:
        """更新 AI 模型配置"""
        new_values = update_data.model_dump(exclude_unset=True)
        response_data = {}

        # 1. 转换键并存库
        for model_type in MODEL_TYPES:
            if model_type in new_values:
                config_key = f"ai_{model_type}_config"
                config_val = new_values[model_type]

                db_config = await crud_system_config.update_by_key(
                    db, config_key=config_key, config_value=config_val, tenant_id=target_tenant_id
                )

                response_val = copy.deepcopy(db_config.config_value)
                response_val = mask_sensitive_data(response_val)
                response_data[model_type] = response_val

        # 2. 清理配置缓存
        try:
            configuration_service.clear_cache(tenant_id=target_tenant_id)
            logger.info(f"🧹 Cleared AI config cache for tenant: {target_tenant_id}")
        except Exception as e:
            logger.error(f"❌ Failed to clear config cache: {e}")

        # 3. 触发 VectorStore 热更新 (仅当更新了 embedding 配置时)
        if "embedding" in new_values:
            _reload_tenant_id = target_tenant_id

            async def _reload_vector_store():
                try:
                    async with asyncio.timeout(10):
                        from app.core.vector.vector_store import VectorStoreManager

                        manager = await VectorStoreManager.get_instance()
                        await manager.reload_credentials(tenant_id=_reload_tenant_id)
                        logger.info("✅ VectorStore credentials reloaded in background")
                except Exception as e:
                    logger.warning(f"⚠️ Vector store reload skipped or failed: {e}")

            asyncio.create_task(_reload_vector_store())

        return response_data

    @staticmethod
    async def test_model_connection(model_type: str, config: Any) -> dict:
        """测试模型连接性"""
        if model_type in ["chat", "vl"]:
            try:
                client = SystemConfigService._create_openai_client(
                    api_key=config.api_key, base_url=config.base_url
                )
                response = await client.chat.completions.create(
                    model=config.model,
                    messages=[{"role": "user", "content": "Hello"}],
                    max_tokens=5,
                )
                return {"details": f"Response: {response.choices[0].message.content[:20]}..."}
            except Exception as e:
                logger.error(f"❌ Chat/VL connection test failed: {e}")
                raise BadRequestException(detail=f"连接失败: {str(e)}")

        elif model_type == "embedding":
            try:
                client = SystemConfigService._create_openai_client(
                    api_key=config.api_key, base_url=config.base_url
                )
                response = await client.embeddings.create(model=config.model, input="Hello world")
                dim = len(response.data[0].embedding)
                return {"dimension": dim}
            except Exception as e:
                logger.error(f"❌ Embedding connection test failed: {e}")
                raise BadRequestException(detail=f"连接失败: {str(e)}")

        elif model_type == "rerank":
            try:
                import httpx

                url = config.base_url.rstrip("/")
                if not url.endswith("/rerank"):
                    url = f"{url}/rerank"

                payload = {
                    "model": config.model,
                    "query": "What is Deep Learning?",
                    "documents": ["Deep Learning is ...", "Hello World"],
                    "top_n": 1,
                }
                headers = {
                    "Authorization": f"Bearer {config.api_key}",
                    "Content-Type": "application/json",
                }

                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(url, json=payload, headers=headers)
                    if resp.status_code != 200:
                        raise BadRequestException(
                            detail=f"请求失败 (Status {resp.status_code}): {resp.text[:100]}"
                        )
                    return {"status": "ok"}
            except Exception as e:
                logger.error(f"❌ Rerank connection test failed: {e}")
                raise BadRequestException(detail=f"连接失败: {str(e)}")

        raise BadRequestException(detail=f"不支持的测试类型: {model_type}")

    @staticmethod
    async def get_doc_processor_config(
        db: AsyncSession, target_tenant_id: int | None, scope: str
    ) -> dict:
        """获取文档处理服务配置 (带平台回退合并逻辑)"""
        # 1. 检查平台回退权限
        platform_fallback_allowed = False
        if scope == "tenant" and target_tenant_id:
            from app.crud.tenant import crud_tenant

            tenant = await crud_tenant.get(db, id=target_tenant_id)
            if tenant and "doc_processors" in (tenant.platform_resources_allowed or []):
                platform_fallback_allowed = True

        # 2. 获取租户自身配置
        with temporary_tenant_context(target_tenant_id):
            config = await crud_system_config.get_by_key(
                db, config_key=DOC_PROCESSOR_CONFIG_KEY, tenant_id=target_tenant_id
            )

        tenant_processors = []
        if config:
            tenant_processors = config.config_value.get("processors", [])
            for p in tenant_processors:
                p["origin"] = "tenant"
                if "id" not in p:
                    from uuid import uuid4

                    p["id"] = str(uuid4())

        # 3. 获取平台配置 (如果允许)
        platform_processors = []
        if platform_fallback_allowed:
            with temporary_tenant_context(None):
                platform_config = await crud_system_config.get_by_key(
                    db, config_key=DOC_PROCESSOR_CONFIG_KEY, tenant_id=None
                )
                if platform_config:
                    platform_processors = platform_config.config_value.get("processors", [])
                    for p in platform_processors:
                        p["origin"] = "platform"
                        if "id" not in p:
                            from uuid import uuid4

                            p["id"] = str(uuid4())

        # 4. 根据视角进行脱敏并合并
        if scope == "tenant":
            if platform_processors:
                platform_processors = mask_sensitive_data(platform_processors)

        return {"processors": tenant_processors + platform_processors}

    @staticmethod
    async def update_doc_processor_config(
        db: AsyncSession, target_tenant_id: int | None, update_data: Any
    ) -> dict:
        """更新文档处理服务配置 (自动过滤平台来源)"""
        config_value = update_data.model_dump(mode="json")
        if "processors" in config_value:
            config_value["processors"] = [
                p for p in config_value["processors"] if p.get("origin") != "platform"
            ]

        db_config = await crud_system_config.update_by_key(
            db,
            config_key=DOC_PROCESSOR_CONFIG_KEY,
            config_value=config_value,
            tenant_id=target_tenant_id,
        )
        return copy.deepcopy(db_config.config_value)

    @staticmethod
    async def test_doc_processor_connection(config: Any) -> dict:
        """测试文档处理服务连接性"""
        try:
            from app.core.doc_processor import DocProcessorFactory

            processor = DocProcessorFactory.create(config)
            is_healthy = await processor.is_healthy()
            if is_healthy:
                return {"status": "healthy"}
            else:
                raise BadRequestException(detail="无法连接到服务或服务异常")
        except Exception as e:
            logger.error(f"❌ Doc processor test failed: {e}")
            raise BadRequestException(detail=f"连接失败: {str(e)}")
