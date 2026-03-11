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
站点管理 API 端点
"""

import logging

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.web.deps import get_current_user_with_tenant, is_demo_tenant
from app.db.database import get_db
from app.models.user import User
from app.schemas.response import ApiResponse, PaginatedResponse
from app.schemas.site import Site, SiteCreate, SiteUpdate
from app.services.site_service import SiteService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=ApiResponse[PaginatedResponse[Site]], operation_id="listAdminSites")
async def list_sites(
    page: int = 1,
    size: int = 10,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_with_tenant),
    is_demo: bool = Depends(is_demo_tenant),
) -> ApiResponse[PaginatedResponse[Site]]:
    sites, paginator = await SiteService.list_sites(db, page, size, status, is_demo)
    return ApiResponse.ok(
        data=PaginatedResponse(
            list=sites,
            pagination=paginator.to_pagination_info(),
        ),
        msg="获取成功",
    )


@router.get("/{site_id}", response_model=ApiResponse[Site], operation_id="getAdminSite")
async def get_site(
    site_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_with_tenant),
    is_demo: bool = Depends(is_demo_tenant),
) -> ApiResponse[Site]:
    site = await SiteService.get_site(db, site_id, is_demo)
    return ApiResponse.ok(data=site, msg="获取成功")


@router.get(":bySlug/{slug}", response_model=ApiResponse[Site], operation_id="getAdminSiteBySlug")
async def get_site_by_slug(
    slug: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_with_tenant),
    is_demo: bool = Depends(is_demo_tenant),
) -> ApiResponse[Site]:
    site = await SiteService.get_site_by_slug(db, slug, is_demo)
    return ApiResponse.ok(data=site, msg="获取成功")


@router.post(
    "",
    response_model=ApiResponse[Site],
    status_code=status.HTTP_201_CREATED,
    operation_id="createAdminSite",
)
async def create_site(
    site_in: SiteCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_with_tenant),
) -> ApiResponse[Site]:
    site = await SiteService.create_site(db, site_in)
    return ApiResponse.ok(data=site, msg="创建成功")


@router.put("/{site_id}", response_model=ApiResponse[Site], operation_id="updateAdminSite")
async def update_site(
    site_id: int,
    site_in: SiteUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_with_tenant),
) -> ApiResponse[Site]:
    site = await SiteService.update_site(db, site_id, site_in)
    return ApiResponse.ok(data=site, msg="更新成功")


@router.delete("/{site_id}", response_model=ApiResponse[None], operation_id="deleteAdminSite")
async def delete_site(
    site_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_with_tenant),
) -> ApiResponse[None]:
    await SiteService.delete_site(db, site_id)
    return ApiResponse.ok(msg="删除成功")
