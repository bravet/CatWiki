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
文件管理接口
提供文件上传、下载、删除等功能
"""

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import Response

from app.core.infra.rustfs import RustFSService
from app.core.web.deps import get_current_user_with_tenant, get_rustfs
from app.models.user import User
from app.schemas.response import ApiResponse, PaginatedResponse
from app.services.file_service import FileService

router = APIRouter()


@router.post(":upload", response_model=ApiResponse[dict], operation_id="uploadAdminFile")
async def upload_file(
    file: UploadFile = File(..., description="要上传的文件"),
    folder: str = Query("uploads", description="存储文件夹"),
    rustfs: RustFSService = Depends(get_rustfs),
    current_user: User = Depends(get_current_user_with_tenant),
) -> ApiResponse[dict]:
    """上传文件到 RustFS"""
    data = await FileService.upload_file(rustfs, file, folder, current_user)
    return ApiResponse.ok(data=data, msg="文件上传成功")


@router.post(":batchUpload", response_model=ApiResponse[dict], operation_id="batchUploadAdminFiles")
async def upload_multiple_files(
    files: list[UploadFile] = File(..., description="要上传的多个文件"),
    folder: str = Query("uploads", description="存储文件夹"),
    rustfs: RustFSService = Depends(get_rustfs),
    current_user: User = Depends(get_current_user_with_tenant),
) -> ApiResponse[dict]:
    """批量上传文件到 RustFS"""
    data = await FileService.batch_upload_files(rustfs, files, folder, current_user)
    return ApiResponse.ok(
        data=data,
        msg=f"批量上传完成，成功 {data['success_count']} 个，失败 {data['error_count']} 个",
    )


@router.get("/{object_name:path}:download", operation_id="downloadAdminFile")
async def download_file(
    object_name: str,
    rustfs: RustFSService = Depends(get_rustfs),
    current_user: User = Depends(get_current_user_with_tenant),
):
    """下载文件"""
    content, content_type, filename = await FileService.download_file(rustfs, object_name)
    return Response(
        content=content,
        media_type=content_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.delete(
    "/{object_name:path}", response_model=ApiResponse[None], operation_id="deleteAdminFile"
)
async def delete_file(
    object_name: str,
    rustfs: RustFSService = Depends(get_rustfs),
    current_user: User = Depends(get_current_user_with_tenant),
) -> ApiResponse[None]:
    """删除文件"""
    await FileService.delete_file(rustfs, object_name)
    return ApiResponse.ok(msg="文件删除成功")


@router.get(
    "", response_model=ApiResponse[PaginatedResponse[dict]], operation_id="listAdminFiles"
)
async def list_files(
    prefix: str = Query("", description="文件路径前缀"),
    recursive: bool = Query(True, description="是否递归列出"),
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页数量"),
    rustfs: RustFSService = Depends(get_rustfs),
    current_user: User = Depends(get_current_user_with_tenant),
) -> ApiResponse[PaginatedResponse[dict]]:
    """列出文件"""
    files, paginator = await FileService.list_files(rustfs, prefix, recursive, page, size)
    return ApiResponse.ok(
        data=PaginatedResponse(list=files, pagination=paginator.to_pagination_info()),
        msg="获取成功",
    )


@router.get(
    "/{object_name:path}:info", response_model=ApiResponse[dict], operation_id="getAdminFileInfo"
)
async def get_file_info(
    object_name: str,
    rustfs: RustFSService = Depends(get_rustfs),
    current_user: User = Depends(get_current_user_with_tenant),
) -> ApiResponse[dict]:
    """获取文件信息"""
    data = await FileService.get_file_info(rustfs, object_name)
    return ApiResponse.ok(data=data, msg="获取成功")


@router.get(
    "/{object_name:path}:presignedUrl",
    response_model=ApiResponse[dict],
    operation_id="getAdminPresignedUrl",
)
async def get_presigned_url(
    object_name: str,
    expires_hours: int = Query(1, ge=1, le=168, description="URL 有效期（小时）"),
    rustfs: RustFSService = Depends(get_rustfs),
    current_user: User = Depends(get_current_user_with_tenant),
) -> ApiResponse[dict]:
    """获取文件的预签名 URL"""
    url = await FileService.get_presigned_url(rustfs, object_name, expires_hours)
    return ApiResponse.ok(
        data={
            "object_name": object_name,
            "url": url,
            "expires_hours": expires_hours,
        },
        msg="获取成功",
    )
