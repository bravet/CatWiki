import logging
import shutil
import tempfile
import time
import uuid
from pathlib import Path

from fastapi import BackgroundTasks, Depends, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.common.document_utils import build_collection_map, enrich_document_dict
from app.core.common.utils import NAMESPACE_CATWIKI, Paginator
from app.core.doc_processor import DocProcessorFactory
from app.core.infra.config import DOC_PROCESSOR_CONFIG_KEY
from app.core.infra.tenant import get_current_tenant, temporary_tenant_context
from app.core.vector.vector_store import VectorStoreManager
from app.core.web.exceptions import BadRequestException, NotFoundException
from app.crud.collection import crud_collection
from app.crud.document import crud_document
from app.crud.site import crud_site
from app.crud.system_config import crud_system_config
from app.crud.tenant import crud_tenant
from app.db.database import AsyncSessionLocal, get_db
from app.models.document import Document as DocumentModel
from app.models.document import DocumentStatus, VectorStatus
from app.schemas.document import DocumentCreate
from app.schemas.system_config import DocProcessorConfig
from app.services.config.configuration_service import configuration_service
from app.services.site_service import SiteService, get_site_service

logger = logging.getLogger(__name__)


class DocumentService:
    def __init__(self, db: AsyncSession, site_service: SiteService):
        self.db = db
        self.site_service = site_service

    def is_vectorizable(self, document: DocumentModel) -> bool:
        """检查文档是否可以向量化"""
        return document.vector_status in (
            VectorStatus.NONE,
            VectorStatus.FAILED,
            VectorStatus.COMPLETED,
            None,
        )

    @staticmethod
    async def process_vectorization_task(document_id: int):
        """处理文档向量化任务（异步后台任务）"""
        task_start_time = time.time()
        logger.info(f"🔄 [Task] 开始处理向量化任务 | DocID: {document_id}")

        async with AsyncSessionLocal() as db:
            try:
                document = await crud_document.get(db, id=document_id)
                if not document:
                    logger.warning(f"⚠️ 文档 {document_id} 不存在，跳过向量化")
                    return

                if document.vector_status != VectorStatus.PENDING:
                    logger.warning(
                        f"⚠️ 文档 {document_id} 状态不为 pending ({document.vector_status})，跳过向量化"
                    )
                    return

                with temporary_tenant_context(document.tenant_id):
                    await crud_document.update_vector_status(
                        db, document_id=document_id, status=VectorStatus.PROCESSING
                    )

                    if not document.content:
                        logger.warning(f"⚠️ 文档 {document_id} 内容为空，无法向量化")
                        await crud_document.update_vector_status(
                            db,
                            document_id=document_id,
                            status=VectorStatus.FAILED,
                            error="文档内容为空",
                        )
                        return

                    vector_store = await VectorStoreManager.get_instance()
                    base_metadata = {
                        "source": "document",
                        "id": str(document.id),
                        "title": document.title,
                        "author": document.author,
                        "site_id": document.site_id,
                        "collection_id": document.collection_id,
                        "tenant_id": document.tenant_id,
                    }

                    from langchain_text_splitters import RecursiveCharacterTextSplitter

                    text_splitter = RecursiveCharacterTextSplitter(
                        chunk_size=1000, chunk_overlap=200, length_function=len
                    )
                    chunks = text_splitter.create_documents(
                        texts=[document.content], metadatas=[base_metadata]
                    )

                    logger.info(
                        f"📄 文档 {document_id} (租户: {document.tenant_id}) 已切分为 {len(chunks)} 个片段"
                    )

                    chunk_ids = []
                    for i, chunk in enumerate(chunks):
                        chunk_id_str = f"{document.id}_chunk_{i}"
                        chunk_uuid = str(uuid.uuid5(NAMESPACE_CATWIKI, chunk_id_str))
                        chunk_ids.append(chunk_uuid)
                        chunk.metadata["id"] = str(document.id)
                        chunk.metadata["chunk_index"] = i

                    await vector_store.delete_by_metadata(key="id", value=str(document.id))

                    if chunks:
                        await vector_store.add_documents(documents=chunks, ids=chunk_ids)

                    await crud_document.update_vector_status(
                        db, document_id=document_id, status=VectorStatus.COMPLETED
                    )
                    total_elapsed = time.time() - task_start_time
                    logger.info(
                        f"✨ [Task] 文档向量化完成! | ID: {document.id} | Chunks: {len(chunks)} | 总耗时: {total_elapsed:.3f}s"
                    )

            except Exception as e:
                logger.error(f"❌ 文档 {document_id} 向量化失败: {e}", exc_info=True)
                try:
                    await crud_document.update_vector_status(
                        db, document_id=document_id, status=VectorStatus.FAILED, error=str(e)
                    )
                except Exception as update_err:
                    logger.warning(f"更新文档 {document_id} 向量化状态失败: {update_err}")

    async def import_document(
        self,
        file: UploadFile,
        site_id: int,
        collection_id: int,
        processor_type: str,
        ocr_enabled: bool,
        extract_images: bool,
        extract_tables: bool,
        current_username: str,
    ) -> dict:
        """导入文档（上传 -> 解析 -> 创建）并返回 enriched dictionary"""
        try:
            active_tenant_id = get_current_tenant()
            await configuration_service.get_embedding_config(tenant_id=active_tenant_id, force=True)
        except Exception as e:
            logger.warning(f"⚠️ 导入文档前配置检查失败: {e}")
            raise BadRequestException(
                detail=f"导入失败：请先在系统设置中完成 Embedding 模型配置。具体原因: {str(e)}"
            )

        site = await crud_site.get(self.db, id=site_id)
        if not site:
            raise BadRequestException(detail=f"站点 {site_id} 不存在")

        filename = file.filename or ""
        suffix = Path(filename).suffix.lower()
        if suffix not in [".pdf", ".jpg", ".jpeg", ".png"]:
            raise BadRequestException(detail="目前仅支持 PDF 和图片文件")

        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                shutil.copyfileobj(file.file, tmp)
                tmp_path = Path(tmp.name)
        except Exception as e:
            logger.error(f"保存上传文件失败: {e}")
            raise BadRequestException(detail="文件上传失败")

        try:
            # 1. 确定授权范围：租户自己的资源 + (如果授权了) 平台共享资源
            accessible_processors = []

            # 获取租户侧配置
            doc_processor_config = await crud_system_config.get_by_key(
                self.db, config_key=DOC_PROCESSOR_CONFIG_KEY, tenant_id=active_tenant_id
            )
            if doc_processor_config:
                tenant_procs = doc_processor_config.config_value.get("processors", [])
                logger.debug(
                    f"🔍 租户侧配置 (T:{active_tenant_id}): found {len(tenant_procs)} processors"
                )
                for p in tenant_procs:
                    p["_source"] = "tenant"
                accessible_processors.extend(tenant_procs)
            else:
                logger.debug(f"🔍 租户侧配置 (T:{active_tenant_id}): None")

            # 检查并拉取平台资源
            platform_fallback_allowed = False
            if active_tenant_id:
                tenant = await crud_tenant.get(self.db, id=active_tenant_id)
                if tenant and "doc_processors" in (tenant.platform_resources_allowed or []):
                    platform_fallback_allowed = True

            if platform_fallback_allowed:
                with temporary_tenant_context(None):
                    platform_config = await crud_system_config.get_by_key(
                        self.db, config_key=DOC_PROCESSOR_CONFIG_KEY, tenant_id=None
                    )
                if platform_config:
                    platform_procs = platform_config.config_value.get("processors", [])
                    logger.debug(f"🔍 平台侧配置: found {len(platform_procs)} processors")
                    for p in platform_procs:
                        # 只有当租户侧没配置同名处理器时，才加入平台配置 (覆盖逻辑)
                        if not any(tp.get("name") == p.get("name") for tp in accessible_processors):
                            p["_source"] = "platform"
                            accessible_processors.append(p)
                else:
                    logger.debug("🔍 平台侧配置 (T:None): None")

            # 2. 精确匹配目标处理器 (必须类型/名称匹配且已启用)
            target_processor_config = None
            for p in accessible_processors:
                # 兼容性处理：如果 type 为枚举对象，先转 string
                p_type = str(p.get("type") or "")
                p_name = str(p.get("name") or "")

                if (p_type == processor_type or p_name == processor_type) and p.get(
                    "enabled", True
                ):
                    target_processor_config = p
                    break

            if not target_processor_config:
                logger.warning(
                    f"❌ 未找到匹配的处理器: type={processor_type}, tenant={active_tenant_id}, "
                    f"platform_allowed={platform_fallback_allowed}, pool_size={len(accessible_processors)}"
                )
                # 记录更多详细信息以便排查
                if accessible_processors:
                    available = [
                        f"{p.get('name')}({p.get('type')}, enabled={p.get('enabled')})"
                        for p in accessible_processors
                    ]
                    logger.warning(f"   可用处理器: {available}")

                raise BadRequestException(
                    detail=f"未找到类型为 {processor_type} 且已启用的文档处理器配置。请前往 [系统设置] 确认相关服务已正确配置并开启。"
                )

            if "config" not in target_processor_config:
                target_processor_config["config"] = {}

            target_processor_config["config"]["is_ocr"] = ocr_enabled
            target_processor_config["config"]["extract_images"] = extract_images
            target_processor_config["config"]["extract_tables"] = extract_tables

            try:
                processor_config_obj = DocProcessorConfig(**target_processor_config)
                processor = DocProcessorFactory.create(processor_config_obj)

                logger.info(
                    f"🚀 开始解析文档: {filename} using {processor_config_obj.type} (Name: {processor_config_obj.name}, OCR={ocr_enabled})"
                )
                start_time = time.time()
                result = await processor.process(tmp_path)
                elapsed = time.time() - start_time
                logger.info(
                    f"✅ 文档解析完成 ({elapsed:.2f}s). Markdown length: {len(result.markdown)}"
                )

            except ValueError as e:
                raise BadRequestException(detail=str(e))
            except Exception as e:
                logger.error(f"文档解析失败: {e}", exc_info=True)
                raise BadRequestException(detail=f"文档解析失败: {str(e)}")

            document_in = DocumentCreate(
                title=filename.replace(suffix, ""),
                content=result.markdown,
                site_id=site_id,
                collection_id=collection_id,
                author=current_username,
                status=DocumentStatus.DRAFT,
            )

            async with self.db.begin():
                document = await crud_document.create(
                    self.db, obj_in=document_in, auto_commit=False
                )
                await self.site_service.increment_article_count(site_id=site_id)

            await self.db.refresh(document)
            document_dict = await enrich_document_dict(document, self.db, crud_collection)
            return document_dict

        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except Exception as e:
                    logger.warning(f"清理临时文件失败: {tmp_path}, {e}")

    async def dispatch_vectorization_tasks(
        self, background_tasks: BackgroundTasks, document_ids: list[int]
    ) -> tuple[list[int], int]:
        """统一处理向量化任务分发"""
        documents = await crud_document.get_multi(self.db, ids=document_ids)
        document_map = {doc.id: doc for doc in documents}

        success_ids = []
        failed_count = 0

        for doc_id in document_ids:
            document = document_map.get(doc_id)
            if document and self.is_vectorizable(document):
                success_ids.append(doc_id)
            else:
                # 说明不可向量化 (is_vectorizable 返回 False)
                logger.warning("文档 %s 当前状态不满足向量化要求", doc_id)
                failed_count += 1

        if not success_ids:
            return [], failed_count

        # 设置为 PENDING
        await crud_document.batch_update_vector_status(
            self.db, document_ids=success_ids, status=VectorStatus.PENDING
        )

        try:
            target_tenant_id = documents[0].tenant_id if documents else None
            await configuration_service.get_embedding_config(tenant_id=target_tenant_id, force=True)
        except Exception as e:
            error_msg = str(e)
            logger.debug(f"Sync configuration check failed: {e}")
            await crud_document.batch_update_vector_status(
                self.db,
                document_ids=success_ids,
                status=VectorStatus.FAILED,
                error=f"配置缺失: {error_msg}",
            )
            raise BadRequestException(detail=f"学习失败：{error_msg}")

        for doc_id in success_ids:
            # 这里的 process_vectorization_task 是静态方法，直接通过类或 self 调用均可
            background_tasks.add_task(self.process_vectorization_task, doc_id)

        return success_ids, failed_count

    async def list_documents(
        self,
        page: int,
        size: int,
        site_id: int | None,
        collection_id: int | None,
        status: str | None,
        vector_status: str | None,
        keyword: str | None,
        order_by: str | None,
        order_dir: str | None,
        exclude_content: bool,
        tenant_id: int | None = None,
        include_site: bool = False,
    ) -> tuple[list[dict], Paginator]:
        """获取文档列表（分页）"""
        paginator = Paginator(page=page, size=size, total=0)

        if collection_id:
            collection_ids = await crud_collection.get_descendant_ids(
                self.db, collection_id=collection_id
            )
        else:
            collection_ids = None

        documents = await crud_document.list(
            self.db,
            site_id=site_id,
            tenant_id=tenant_id,
            collection_ids=collection_ids,
            status=status,
            vector_status=vector_status,
            keyword=keyword,
            skip=paginator.skip,
            limit=paginator.size,
            order_by=order_by,
            order_dir=order_dir,
            include_site=include_site,
        )
        paginator.total = await crud_document.count(
            self.db,
            site_id=site_id,
            tenant_id=tenant_id,
            collection_ids=collection_ids,
            status=status,
            vector_status=vector_status,
            keyword=keyword,
        )

        # 批量加载合集信息
        doc_collection_ids = list(
            set([doc.collection_id for doc in documents if doc.collection_id])
        )
        collection_map = await build_collection_map(self.db, crud_collection, doc_collection_ids)

        enriched_docs = []
        for doc in documents:
            doc_dict = await enrich_document_dict(
                doc,
                self.db,
                crud_collection,
                collection_map=collection_map,
                include_site_info=include_site,
            )
            if exclude_content:
                doc_dict["content"] = None
            enriched_docs.append(doc_dict)

        return enriched_docs, paginator

    async def get_document(self, document_id: int) -> dict:
        """获取文档详情"""
        document = await crud_document.get_with_related_site(self.db, id=document_id)
        if not document:
            raise NotFoundException(detail=f"文档 {document_id} 不存在")
        return await enrich_document_dict(
            document, self.db, crud_collection, include_site_info=True
        )

    async def create_document(self, document_in: DocumentCreate) -> dict:
        """创建文档"""
        site = await crud_site.get(self.db, id=document_in.site_id)
        if not site:
            raise BadRequestException(detail=f"站点 {document_in.site_id} 不存在")

        async with self.db.begin():
            document = await crud_document.create(self.db, obj_in=document_in, auto_commit=False)
            await self.site_service.increment_article_count(site_id=document_in.site_id)

        await self.db.refresh(document)
        return await enrich_document_dict(document, self.db, crud_collection)

    async def update_document(self, document_id: int, document_in: any) -> dict:
        """更新文档"""
        document = await crud_document.get(self.db, id=document_id)
        if not document:
            raise NotFoundException(detail=f"文档 {document_id} 不存在")

        document = await crud_document.update(self.db, db_obj=document, obj_in=document_in)
        return await enrich_document_dict(document, self.db, crud_collection)

    async def delete_document(self, document_id: int) -> None:
        """删除文档"""
        doc = await crud_document.get(self.db, id=document_id)
        if not doc:
            raise NotFoundException(detail=f"文档 {document_id} 不存在")

        site_id = doc.site_id

        # 1. 删除向量数据 (非强制)
        try:
            from app.core.vector.vector_store import VectorStoreManager

            vector_store = await VectorStoreManager.get_instance()
            await vector_store.delete_by_metadata(key="id", value=str(document_id))
        except Exception as e:
            logger.warning(f"删除文档向量失败: {e}")

        async with self.db.begin():
            await crud_document.delete(self.db, id=document_id, auto_commit=False)
            await self.site_service.decrement_article_count(site_id=site_id)

    async def remove_document_vector(self, document_id: int) -> dict:
        """手动清空文档向量数据"""
        doc = await crud_document.get(self.db, id=document_id)
        if not doc:
            raise NotFoundException(detail=f"文档 {document_id} 不存在")

        from app.core.vector.vector_store import VectorStoreManager

        vector_store = await VectorStoreManager.get_instance()
        await vector_store.delete_by_metadata(key="id", value=str(document_id))

        await crud_document.update(self.db, db_obj=doc, obj_in={"vector_status": VectorStatus.NONE})
        return await enrich_document_dict(doc, self.db, crud_collection)

    async def get_document_chunks(self, document_id: int) -> list[dict]:
        """获取文档切片"""
        document = await crud_document.get(self.db, id=document_id)
        if not document:
            raise NotFoundException(detail=f"文档 {document_id} 不存在")

        try:
            vector_store = await VectorStoreManager.get_instance()
            return await vector_store.get_chunks_by_metadata(key="id", value=str(document_id))
        except Exception as e:
            logger.error(f"Failed to get chunks for doc {document_id}: {e}")
            return []

    async def vectorize_single_document(
        self, background_tasks: BackgroundTasks, document_id: int
    ) -> dict:
        """向量化单个文档"""
        document = await crud_document.get(self.db, id=document_id)
        if not document:
            raise NotFoundException(detail=f"文档 {document_id} 不存在")

        # 使用已有的批量分发逻辑
        success_ids, _ = await self.dispatch_vectorization_tasks(background_tasks, [document_id])

        if not success_ids:
            # 说明不可向量化 (can_vectorize 返回 False)
            raise BadRequestException(
                detail=f"文档当前状态为 {document.vector_status}，无法重新学习"
            )

        # 重新获取文档以返回最新状态
        document = await crud_document.get(self.db, id=document_id)
        return await enrich_document_dict(document, self.db, crud_collection)

    async def get_client_document(
        self,
        document_id: int,
        ip_address: str | None = None,
        user_agent: str | None = None,
        referer: str | None = None,
    ) -> dict:
        """获取已发布文档详情（客户端，增加浏览量）"""
        document = await crud_document.get_with_related_site(self.db, id=document_id)
        if not document or document.status != DocumentStatus.PUBLISHED:
            raise NotFoundException(detail=f"文档 {document_id} 不存在")

        # 自动增加浏览量并记录浏览事件
        document = await crud_document.increment_views(
            self.db,
            document_id=document_id,
            site_id=document.site_id,
            tenant_id=document.tenant_id,
            ip_address=ip_address,
            user_agent=user_agent,
            referer=referer,
        )

        return await enrich_document_dict(
            document, self.db, crud_collection, include_site_info=True
        )


def get_document_service(
    db: AsyncSession = Depends(get_db),
    site_service: SiteService = Depends(get_site_service),
) -> DocumentService:
    """获取 DocumentService 实例的依赖注入函数"""
    return DocumentService(db, site_service)
