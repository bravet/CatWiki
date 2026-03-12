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

from app.schemas.response import ApiResponse, HealthResponse
from app.services.health_service import HealthService, get_health_service

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "",
    response_model=ApiResponse[HealthResponse],
    summary="健康检查 (客户端)",
    description="检查 API 服务状态并返回版本信息",
    operation_id="getClientHealth",
)
async def health_check(
    service: HealthService = Depends(get_health_service),
) -> ApiResponse[HealthResponse]:
    """
    客户端专用的健康检查接口
    """
    health_status = await service.get_health_status(detailed=False)
    return ApiResponse.ok(data=health_status)
