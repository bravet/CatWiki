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

from fastapi import APIRouter, Depends, Query

from app.core.infra.cache import cached_response
from app.schemas.response import ApiResponse, PaginatedResponse
from app.schemas.site import ClientSite
from app.services.site_service import SiteService, get_site_service

router = APIRouter()


@router.get(
    "", response_model=ApiResponse[PaginatedResponse[ClientSite]], operation_id="listClientSites"
)
async def list_active_sites(
    page: int = 1,
    size: int = 10,
    tenant_id: int | None = Query(None, description="租户ID"),
    tenant_slug: str | None = Query(None, description="租户标识 (Portal 入口有效)"),
    keyword: str | None = Query(None, description="搜索关键词（站点名称或描述）"),
    service: SiteService = Depends(get_site_service),
) -> ApiResponse[PaginatedResponse[ClientSite]]:
    """获取激活的站点列表（客户端）

    - 不传 tenant_id：返回所有租户的激活站点（站点广场）
    - 传 tenant_id：仅返回该租户下的激活站点
    """
    client_sites, paginator = await service.list_client_sites(
        page, size, tenant_id, tenant_slug, keyword
    )

    return ApiResponse.ok(
        data=PaginatedResponse(
            list=client_sites,
            pagination=paginator.to_pagination_info(),
        ),
        msg="获取成功",
    )


@router.get(
    ":bySlug/{slug}", response_model=ApiResponse[ClientSite], operation_id="getClientSiteBySlug"
)
@cached_response(ttl=10, key_prefix="client:site:slug")  # 降低缓存时间到 10 秒
async def get_site_by_slug(
    slug: str,
    service: SiteService = Depends(get_site_service),
) -> ApiResponse[ClientSite]:
    """通过 slug 获取站点详情（客户端）"""
    client_site = await service.get_client_site(slug=slug)
    return ApiResponse.ok(data=client_site, msg="获取成功")


@router.get("/{site_id}", response_model=ApiResponse[ClientSite], operation_id="getClientSite")
@cached_response(ttl=10, key_prefix="client:site:id")  # 降低缓存时间到 10 秒
async def get_site(
    site_id: int,
    service: SiteService = Depends(get_site_service),
) -> ApiResponse[ClientSite]:
    """获取站点详情（客户端）"""
    client_site = await service.get_client_site(site_id=site_id)
    return ApiResponse.ok(data=client_site, msg="获取成功")
