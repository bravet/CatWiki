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
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.schemas.collection import CollectionTree
from app.schemas.response import ApiResponse
from app.services.collection_service import CollectionService

router = APIRouter()


@router.get(
    ":tree",
    response_model=ApiResponse[list[CollectionTree]],
    operation_id="getClientCollectionTree",
)
async def get_collection_tree(
    site_id: int = Query(..., description="站点ID"),
    include_documents: bool = Query(False, description="是否包含文档节点"),
    tenant_id: int | None = Query(None, description="租户ID"),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[CollectionTree]]:
    """获取合集树形结构（客户端）"""
    tree = await CollectionService.get_collection_tree(
        db,
        site_id=site_id,
        show_type="all" if include_documents else "collection",
        tenant_id=tenant_id,
        status="published",
    )
    return ApiResponse.ok(data=tree, msg="获取成功")
