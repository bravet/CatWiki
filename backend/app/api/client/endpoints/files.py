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
客户端文件接口
提供文件下载和访问功能（只读）
"""

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from app.schemas.response import ApiResponse
from app.services.file_service import FileService, get_file_service

router = APIRouter()


@router.get("/{object_name:path}:download", operation_id="downloadClientFile")
async def download_file(
    object_name: str,
    service: FileService = Depends(get_file_service),
):
    """下载文件（客户端）"""
    content, content_type, filename = await service.download_file(object_name)
    return Response(
        content=content,
        media_type=content_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get(
    "/{object_name:path}:info", response_model=ApiResponse[dict], operation_id="getClientFileInfo"
)
async def get_file_info(
    object_name: str,
    service: FileService = Depends(get_file_service),
) -> ApiResponse[dict]:
    """获取文件信息（客户端）"""
    data = await service.get_client_file_info(object_name)
    return ApiResponse.ok(data=data, msg="获取成功")


@router.get(
    "/{object_name:path}:presignedUrl",
    # 注意：该端点名称虽然保留，但实际行为依赖 bucket 公开性
    response_model=ApiResponse[dict],
    operation_id="getClientPresignedUrl",
)
async def get_presigned_url(
    object_name: str,
    # 客户端接口参数 expires_hours 虽然在旧代码里有 Query，但实际上 get_public_url(False) 并不使用它。
    # 这里我们保留参数以保持接口兼容，但不传递给 get_public_url。
    expires_hours: int = Query(1, ge=1, le=24, description="URL 有效期（小时，最长 24 小时）"),
    service: FileService = Depends(get_file_service),
) -> ApiResponse[dict]:
    """获取文件的访问 URL（客户端）"""
    url = await service.get_public_url(object_name)
    return ApiResponse.ok(
        data={
            "object_name": object_name,
            "url": url,
        },
        msg="获取成功",
    )
