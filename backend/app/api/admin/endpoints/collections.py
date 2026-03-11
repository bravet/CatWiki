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
合集管理 API 端点
"""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.web.deps import get_current_user_with_tenant, get_valid_site
from app.db.database import get_db
from app.models.site import Site
from app.models.user import User
from app.schemas.collection import (
    Collection,
    CollectionCreate,
    CollectionTree,
    CollectionUpdate,
    MoveCollectionRequest,
)
from app.schemas.response import ApiResponse, PaginatedResponse
from app.services.collection_service import CollectionService

router = APIRouter()


@router.get(
    "",
    response_model=ApiResponse[PaginatedResponse[Collection]],
    operation_id="listAdminCollections",
)
async def list_collections(
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页大小"),
    parent_id: int | None = Query(None, description="父合集ID，为空则获取根合集"),
    db: AsyncSession = Depends(get_db),
    site: Site = Depends(get_valid_site),
    current_user: User = Depends(get_current_user_with_tenant),
) -> ApiResponse[PaginatedResponse[Collection]]:
    """获取合集列表"""
    collections, paginator = await CollectionService.list_collections(
        db,
        site_id=site.id,
        tenant_id=current_user.tenant_id,
        parent_id=parent_id,
        page=page,
        size=size,
    )
    return ApiResponse.ok(
        data=PaginatedResponse(
            list=collections,
            pagination=paginator.to_pagination_info(),
        ),
        msg="获取成功",
    )


@router.get(
    ":tree", response_model=ApiResponse[list[CollectionTree]], operation_id="getAdminCollectionTree"
)
async def get_collection_tree(
    type: str | None = Query(
        None, description="树节点类型：不指定则显示合集和文档，'collection'则只显示合集"
    ),
    db: AsyncSession = Depends(get_db),
    site: Site = Depends(get_valid_site),
    current_user: User = Depends(get_current_user_with_tenant),
) -> ApiResponse[list[CollectionTree]]:
    tree = await CollectionService.get_collection_tree(
        db, site_id=site.id, show_type=type, tenant_id=current_user.tenant_id
    )
    return ApiResponse.ok(data=tree, msg="获取成功")


@router.get(
    "/{collection_id}", response_model=ApiResponse[Collection], operation_id="getAdminCollection"
)
async def get_collection(
    collection_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_with_tenant),
) -> ApiResponse[Collection]:
    """获取合集详情"""
    collection = await CollectionService.get_collection(
        db, collection_id=collection_id, tenant_id=current_user.tenant_id
    )
    return ApiResponse.ok(data=collection, msg="获取成功")


@router.post(
    "",
    response_model=ApiResponse[Collection],
    status_code=status.HTTP_201_CREATED,
    operation_id="createAdminCollection",
)
async def create_collection(
    collection_in: CollectionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_with_tenant),
) -> ApiResponse[Collection]:
    """创建合集"""
    collection = await CollectionService.create_collection(
        db, collection_in, tenant_id=current_user.tenant_id
    )
    return ApiResponse.ok(data=collection, msg="创建成功")


@router.put(
    "/{collection_id}", response_model=ApiResponse[Collection], operation_id="updateAdminCollection"
)
async def update_collection(
    collection_id: int,
    collection_in: CollectionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_with_tenant),
) -> ApiResponse[Collection]:
    """更新合集"""
    collection = await CollectionService.update_collection(
        db, collection_id, collection_in, tenant_id=current_user.tenant_id
    )
    return ApiResponse.ok(data=collection, msg="更新成功")


@router.delete(
    "/{collection_id}", response_model=ApiResponse[None], operation_id="deleteAdminCollection"
)
async def delete_collection(
    collection_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_with_tenant),
) -> ApiResponse[None]:
    """删除合集"""
    await CollectionService.delete_collection(db, collection_id, tenant_id=current_user.tenant_id)
    return ApiResponse.ok(msg="删除成功")


@router.post(
    "/{collection_id}:move",
    response_model=ApiResponse[Collection],
    operation_id="moveAdminCollection",
)
async def move_collection(
    collection_id: int,
    move_request: MoveCollectionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_with_tenant),
) -> ApiResponse[Collection]:
    """
    移动合集到新位置

    这个接口会：
    1. 更新合集的 parent_id
    2. 重新计算目标父级下所有合集的 order，确保顺序连续
    """
    collection = await CollectionService.move_collection(
        db,
        collection_id,
        move_request.target_parent_id,
        move_request.target_position,
        tenant_id=current_user.tenant_id,
    )
    return ApiResponse.ok(data=collection, msg="移动成功")
