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

"""
系统配置 API 端点
"""

import logging
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.common.masking import mask_sensitive_data
from app.core.infra.tenant import temporary_tenant_context
from app.core.web.deps import get_current_user_with_tenant
from app.core.web.exceptions import NotFoundException
from app.crud.system_config import crud_system_config
from app.db.database import get_db
from app.models.user import User
from app.schemas.response import ApiResponse
from app.schemas.system_config import (
    AIConfigUpdate,
    DocProcessorsUpdate,
    SystemConfigResponse,
    TestConnectionRequest,
    TestDocProcessorRequest,
)
from app.services.system_config_service import SystemConfigService

router = APIRouter()
logger = logging.getLogger(__name__)

# 模型类型常量
MODEL_TYPES = ["chat", "embedding", "rerank", "vl"]


@router.get(
    "/ai-config",
    response_model=ApiResponse[SystemConfigResponse | None],
    operation_id="getAdminAiConfig",
)
async def get_ai_config(
    scope: Literal["platform", "tenant"] = "tenant",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_with_tenant),
) -> ApiResponse[SystemConfigResponse | None]:
    """
    获取 AI 模型配置
    """
    target_tenant_id = SystemConfigService.resolve_target_tenant_id(scope)
    logger.info(
        "🧭 [SystemConfig] get_ai_config scope=%s target_tenant_id=%s", scope, target_tenant_id
    )

    # 1. 获取基础配置
    tenant_config_value = await SystemConfigService.get_ai_config(db, target_tenant_id) or {
        "chat": {},
        "embedding": {},
        "rerank": {},
        "vl": {},
    }

    # 2. 检查平台回退权限
    platform_defaults = {}
    if scope == "tenant" and target_tenant_id:
        from app.crud.tenant import crud_tenant

        tenant = await crud_tenant.get(db, id=target_tenant_id)
        if tenant and "models" in (tenant.platform_resources_allowed or []):
            from app.core.infra.config_resolver import ConfigResolver

            platform_defaults = {
                "chat": await ConfigResolver.resolve_section("chat", None),
                "embedding": await ConfigResolver.resolve_section("embedding", None),
                "rerank": await ConfigResolver.resolve_section("rerank", None),
                "vl": await ConfigResolver.resolve_section("vl", None),
            }
            # 对平台默认配置进行脱敏
            platform_defaults = mask_sensitive_data(platform_defaults)

    config_response = SystemConfigResponse(
        id=0,
        tenant_id=target_tenant_id,
        config_key="ai_config",
        config_value=tenant_config_value,
        is_active=True,
        created_at=datetime.now(),
        updated_at=datetime.now(),
        platform_defaults=platform_defaults,
    )

    return ApiResponse.ok(data=config_response, msg="获取成功")


@router.put(
    "/ai-config",
    response_model=ApiResponse[SystemConfigResponse],
    operation_id="updateAdminAiConfig",
)
async def update_ai_config(
    config_in: AIConfigUpdate,
    scope: Literal["platform", "tenant"] = "tenant",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_with_tenant),
) -> ApiResponse[SystemConfigResponse]:
    """
    更新 AI 模型配置 (支持局部更新)
    """
    target_tenant_id = SystemConfigService.resolve_target_tenant_id(scope)
    logger.info(
        "🧭 [SystemConfig] update_ai_config scope=%s target_tenant_id=%s", scope, target_tenant_id
    )

    updated_values = await SystemConfigService.update_ai_config(db, target_tenant_id, config_in)

    response_data = SystemConfigResponse(
        id=0,
        config_key="ai_config",
        config_value=updated_values,
        is_active=True,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )

    return ApiResponse.ok(data=response_data, msg="AI 配置更新成功")


@router.delete("/{config_key}", response_model=ApiResponse[dict], operation_id="deleteAdminConfig")
async def delete_config(
    config_key: str,
    scope: Literal["platform", "tenant"] = "tenant",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_with_tenant),
) -> ApiResponse[dict]:
    """
    删除指定配置
    """
    target_tenant_id = SystemConfigService.resolve_target_tenant_id(scope)
    logger.info(
        "🧭 [SystemConfig] delete_config scope=%s target_tenant_id=%s key=%s",
        scope,
        target_tenant_id,
        config_key,
    )

    with temporary_tenant_context(target_tenant_id):
        db_config = await crud_system_config.get_by_key(
            db, config_key=config_key, tenant_id=target_tenant_id
        )

    if not db_config:
        raise NotFoundException(detail=f"配置 {config_key} 不存在")

    await db.delete(db_config)
    await db.commit()

    return ApiResponse.ok(data={"deleted": True}, msg="配置删除成功")


@router.post(
    "/ai-config/test-connection",
    response_model=ApiResponse[dict],
    operation_id="testModelConnection",
)
async def test_model_connection(
    request: TestConnectionRequest,
    scope: Literal["platform", "tenant"] = "tenant",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_with_tenant),
) -> ApiResponse[dict]:
    """
    测试模型连接性
    """
    target_tenant_id = SystemConfigService.resolve_target_tenant_id(scope)
    logger.info(
        "🧭 [SystemConfig] test_model_connection scope=%s target_tenant_id=%s model_type=%s",
        scope,
        target_tenant_id,
        request.model_type,
    )

    result = await SystemConfigService.test_model_connection(request.model_type, request.config)
    return ApiResponse.ok(data=result, msg="连接成功")


# ============ 文档处理服务配置端点 ============


@router.get(
    "/doc-processor",
    response_model=ApiResponse[dict | None],
    operation_id="getAdminDocProcessorConfig",
)
async def get_doc_processor_config(
    scope: Literal["platform", "tenant"] = "tenant",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_with_tenant),
) -> ApiResponse[dict | None]:
    """
    获取文档处理服务配置
    """
    target_tenant_id = SystemConfigService.resolve_target_tenant_id(scope)
    logger.info(
        "🧭 [SystemConfig] get_doc_processor_config scope=%s target_tenant_id=%s",
        scope,
        target_tenant_id,
    )

    response_val = await SystemConfigService.get_doc_processor_config(db, target_tenant_id, scope)
    return ApiResponse.ok(data=response_val, msg="获取成功")


@router.put(
    "/doc-processor", response_model=ApiResponse[dict], operation_id="updateAdminDocProcessorConfig"
)
async def update_doc_processor_config(
    config_in: DocProcessorsUpdate,
    scope: Literal["platform", "tenant"] = "tenant",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_with_tenant),
) -> ApiResponse[dict]:
    """
    更新文档处理服务配置
    """
    target_tenant_id = SystemConfigService.resolve_target_tenant_id(scope)
    logger.info(
        "🧭 [SystemConfig] update_doc_processor_config scope=%s target_tenant_id=%s",
        scope,
        target_tenant_id,
    )

    response_val = await SystemConfigService.update_doc_processor_config(
        db, target_tenant_id, config_in
    )
    return ApiResponse.ok(data=response_val, msg="文档处理服务配置更新成功")


@router.post(
    "/doc-processor/test-connection",
    response_model=ApiResponse[dict],
    operation_id="testDocProcessorConnection",
)
async def test_doc_processor_connection(
    request: TestDocProcessorRequest,
    scope: Literal["platform", "tenant"] = "tenant",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_with_tenant),
) -> ApiResponse[dict]:
    """
    测试文档处理服务连接性
    """
    target_tenant_id = SystemConfigService.resolve_target_tenant_id(scope)
    logger.info(
        "🧭 [SystemConfig] test_doc_processor_connection scope=%s target_tenant_id=%s",
        scope,
        target_tenant_id,
    )

    result = await SystemConfigService.test_doc_processor_connection(request.config)
    return ApiResponse.ok(data=result, msg="连接成功")
