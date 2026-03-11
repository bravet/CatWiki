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

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.schemas.response import ApiResponse, HealthResponse
from app.services.health_service import HealthService

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "",
    # 由于 HealthResponse 可能需要匹配 HealthService 返回的结构，如果 schema 有差异可能需要更新。
    response_model=ApiResponse[HealthResponse],
    summary="健康检查",
    description="检查 API 服务、数据库连接和对象存储状态",
    operation_id="getAdminHealth",
)
async def health_check(
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[HealthResponse]:
    """
    增强的健康检查接口 (Admin)
    - 检查 API 服务状态
    - 检查数据库连接状态
    - 检查 RustFS 对象存储状态 (Detailed)
    - 返回版本和环境信息
    """
    health_status = await HealthService.get_health_status(db, detailed=True)
    return ApiResponse.ok(data=health_status)
