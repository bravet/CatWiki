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
文档管理 API 端点
"""

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.web.deps import get_current_user_with_tenant, get_db
from app.core.web.exceptions import BadRequestException
from app.models.user import User
from app.schemas.document import (
    Document,
    DocumentCreate,
    DocumentUpdate,
    VectorizeRequest,
    VectorizeResponse,
    VectorRetrieveRequest,
    VectorRetrieveResult,
)
from app.schemas.response import ApiResponse, PaginatedResponse
from app.services.document_service import DocumentService

router = APIRouter()
logger = logging.getLogger(__name__)


# ============ 辅助函数 ============


@router.get(
    "", response_model=ApiResponse[PaginatedResponse[Document]], operation_id="listAdminDocuments"
)
async def list_documents(
    page: int = 1,
    size: int = 10,
    site_id: int | None = Query(None, description="站点ID"),
    collection_id: int | None = Query(None, description="合集ID"),
    status: str | None = Query(None, description="状态过滤: published, draft"),
    vector_status: str | None = Query(
        None, description="向量化状态过滤: none, pending, processing, completed, failed"
    ),
    keyword: str | None = Query(None, description="搜索关键词"),
    order_by: str | None = Query(None, description="排序字段: views, created_at, updated_at"),
    order_dir: str | None = Query("desc", description="排序方向: asc, desc"),
    exclude_content: bool = Query(True, description="是否排除文档内容（用于列表展示，提升性能）"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_with_tenant),
) -> ApiResponse[PaginatedResponse[Document]]:
    enriched_docs, paginator = await DocumentService.list_documents(
        db,
        page,
        size,
        site_id,
        collection_id,
        status,
        vector_status,
        keyword,
        order_by,
        order_dir,
        exclude_content,
        tenant_id=current_user.tenant_id,
    )
    return ApiResponse.ok(
        data=PaginatedResponse(
            list=enriched_docs,
            pagination=paginator.to_pagination_info(),
        ),
        msg="获取成功",
    )


@router.get("/{document_id}", response_model=ApiResponse[Document], operation_id="getAdminDocument")
async def get_document(
    document_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_with_tenant),
) -> ApiResponse[Document]:
    document_dict = await DocumentService.get_document(db, document_id)
    return ApiResponse.ok(data=document_dict, msg="获取成功")


@router.post(
    "",
    response_model=ApiResponse[Document],
    status_code=status.HTTP_201_CREATED,
    operation_id="createAdminDocument",
)
async def create_document(
    document_in: DocumentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_with_tenant),
) -> ApiResponse[Document]:
    document_dict = await DocumentService.create_document(db, document_in)
    return ApiResponse.ok(data=document_dict, msg="创建成功")


@router.post(
    "/import",
    response_model=ApiResponse[Document],
    status_code=status.HTTP_201_CREATED,
    operation_id="importDocument",
)
async def import_document(
    file: UploadFile = File(...),
    site_id: int = Form(...),
    collection_id: int = Form(...),
    processor_type: str = Form("MinerU"),
    ocr_enabled: bool = Form(False),
    extract_images: bool = Form(False),
    extract_tables: bool = Form(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_with_tenant),
) -> ApiResponse[Document]:
    """
    导入文档 (上传 -> 解析 -> 创建)
    """
    document_dict = await DocumentService.import_document(
        db=db,
        file=file,
        site_id=site_id,
        collection_id=collection_id,
        processor_type=processor_type,
        ocr_enabled=ocr_enabled,
        extract_images=extract_images,
        extract_tables=extract_tables,
        current_username=current_user.name or current_user.email,
    )
    return ApiResponse.ok(data=document_dict, msg="文档导入成功")


@router.put(
    "/{document_id}", response_model=ApiResponse[Document], operation_id="updateAdminDocument"
)
async def update_document(
    document_id: int,
    document_in: DocumentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_with_tenant),
) -> ApiResponse[Document]:
    document_dict = await DocumentService.update_document(db, document_id, document_in)
    return ApiResponse.ok(data=document_dict, msg="更新成功")


@router.delete(
    "/{document_id}", response_model=ApiResponse[None], operation_id="deleteAdminDocument"
)
async def delete_document(
    document_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_with_tenant),
) -> ApiResponse[None]:
    await DocumentService.delete_document(db, document_id)
    return ApiResponse.ok(msg="删除成功")


# ============ 向量化相关接口 ============


@router.post(
    ":batchVectorize",
    response_model=ApiResponse[VectorizeResponse],
    operation_id="batchVectorizeAdminDocuments",
)
async def vectorize_documents(
    request: VectorizeRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_with_tenant),
) -> ApiResponse[VectorizeResponse]:
    """批量向量化文档（将文档状态设置为 pending，并启动向量化后台任务）"""
    if not request.document_ids:
        raise BadRequestException(detail="文档ID列表不能为空")

    success_ids, failed_count = await DocumentService.dispatch_vectorization_tasks(
        db, background_tasks, request.document_ids
    )

    return ApiResponse.ok(
        data=VectorizeResponse(
            success_count=len(success_ids), failed_count=failed_count, document_ids=success_ids
        ),
        msg=f"已将 {len(success_ids)} 个文档加入学习队列",
    )


@router.post(
    "/{document_id}:vectorize",
    response_model=ApiResponse[Document],
    operation_id="vectorizeAdminDocument",
)
async def vectorize_single_document(
    document_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_with_tenant),
) -> ApiResponse[Document]:
    document_dict = await DocumentService.vectorize_single_document(
        db, background_tasks, document_id
    )
    return ApiResponse.ok(data=document_dict, msg="已加入学习队列")


@router.post(
    "/{document_id}:removeVector",
    response_model=ApiResponse[Document],
    operation_id="removeAdminDocumentVector",
)
async def remove_document_vector(
    document_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_with_tenant),
) -> ApiResponse[Document]:
    document_dict = await DocumentService.remove_document_vector(db, document_id)
    return ApiResponse.ok(data=document_dict, msg="已移除向量数据")


@router.get(
    "/{document_id}/chunks",
    response_model=ApiResponse[list[dict]],
    operation_id="getAdminDocumentChunks",
)
async def get_document_chunks(
    document_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_with_tenant),
) -> ApiResponse[list[dict]]:
    chunks = await DocumentService.get_document_chunks(db, document_id)
    return ApiResponse.ok(data=chunks, msg="获取成功")


@router.post(
    "/retrieve", response_model=ApiResponse[VectorRetrieveResult], operation_id="retrieveDocuments"
)
async def retrieve_vectors(
    request: VectorRetrieveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_with_tenant),
) -> ApiResponse[VectorRetrieveResult]:
    """
    语义检索向量数据库 (delegates to RAGService)
    """
    try:
        from app.services.rag import RAGService

        # 转换过滤器格式 (Schema 应该兼容，但为了保险起见，明确这里是 VectorRetrieveRequest.filter -> VectorRetrieveFilter)
        # 实际上 Pydantic 模型是一致的

        results = await RAGService.retrieve(
            query=request.query,
            k=request.k,
            threshold=request.threshold,
            filter=request.filter,
            enable_rerank=request.enable_rerank,
            rerank_k=request.rerank_k,
        )

        return ApiResponse.ok(data=VectorRetrieveResult(list=results), msg="检索成功")

    except Exception as e:
        logger.error(f"检索失败: {e}", exc_info=True)
        return ApiResponse.ok(data=VectorRetrieveResult(list=[]), msg=f"检索失败: {str(e)}")
