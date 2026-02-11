# Copyright 2024 CatWiki Authors
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
租户管理 API 端点
"""

import logging
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user_with_tenant
from app.core.exceptions import ForbiddenException
from app.crud.tenant import crud_tenant
from app.db.database import get_db
from app.models.user import User, UserRole
from app.schemas.response import ApiResponse, PaginatedResponse
from app.schemas.tenant import TenantSchema, TenantCreate, TenantUpdate
from app.core.utils import Paginator
from app.core.exceptions import NotFoundException

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "", response_model=ApiResponse[PaginatedResponse[TenantSchema]], operation_id="listAdminTenants"
)
async def list_tenants(
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(10, ge=1, le=100, description="每页数量"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_with_tenant),
) -> ApiResponse[PaginatedResponse[TenantSchema]]:
    """
    获取租户列表
    仅限系统管理员 (ADMIN) 访问
    """
    if current_user.role != UserRole.ADMIN:
        raise ForbiddenException(detail="权限不足，仅限系统管理员访问")

    total = await crud_tenant.count(db)
    paginator = Paginator(page=page, size=size, total=total)
    
    tenants = await crud_tenant.list(
        db, 
        skip=paginator.skip, 
        limit=paginator.size,
        order_by="created_at",
        order_dir="desc"
    )

    return ApiResponse.ok(
        data=PaginatedResponse(
            list=tenants,
            pagination=paginator.to_pagination_info()
        ),
        msg="获取成功"
    )


@router.post(
    "", response_model=ApiResponse[TenantSchema], operation_id="createAdminTenant"
)
async def create_tenant(
    tenant_in: TenantCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_with_tenant),
) -> ApiResponse[TenantSchema]:
    """创建新租户"""
    if current_user.role != UserRole.ADMIN:
        raise ForbiddenException(detail="权限不足，仅限系统管理员访问")
    
    tenant = await crud_tenant.create(db, obj_in=tenant_in)
    return ApiResponse.ok(data=tenant, msg="创建成功")


@router.get(
    "/{tenant_id}", response_model=ApiResponse[TenantSchema], operation_id="getAdminTenant"
)
async def get_tenant(
    tenant_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_with_tenant),
) -> ApiResponse[TenantSchema]:
    """获取租户详情"""
    if current_user.role != UserRole.ADMIN:
        raise ForbiddenException(detail="权限不足，仅限系统管理员访问")
        
    tenant = await crud_tenant.get(db, id=tenant_id)
    if not tenant:
        raise NotFoundException(detail="租户不存在")
        
    return ApiResponse.ok(data=tenant, msg="获取成功")


@router.put(
    "/{tenant_id}", response_model=ApiResponse[TenantSchema], operation_id="updateAdminTenant"
)
async def update_tenant(
    tenant_id: int,
    tenant_in: TenantUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_with_tenant),
) -> ApiResponse[TenantSchema]:
    """更新租户"""
    if current_user.role != UserRole.ADMIN:
        raise ForbiddenException(detail="权限不足，仅限系统管理员访问")
        
    tenant = await crud_tenant.get(db, id=tenant_id)
    if not tenant:
        raise NotFoundException(detail="租户不存在")
        
    tenant = await crud_tenant.update(db, db_obj=tenant, obj_in=tenant_in)
    return ApiResponse.ok(data=tenant, msg="更新成功")


@router.delete(
    "/{tenant_id}", response_model=ApiResponse[None], operation_id="deleteAdminTenant"
)
async def delete_tenant(
    tenant_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_with_tenant),
) -> ApiResponse[None]:
    """删除租户"""
    if current_user.role != UserRole.ADMIN:
        raise ForbiddenException(detail="权限不足，仅限系统管理员访问")
        
    tenant = await crud_tenant.get(db, id=tenant_id)
    if not tenant:
        raise NotFoundException(detail="租户不存在")
        
    await crud_tenant.delete(db, id=tenant_id)
    return ApiResponse.ok(msg="删除成功")
