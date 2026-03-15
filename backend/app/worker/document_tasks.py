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
from pathlib import Path

from app.db.database import AsyncSessionLocal

logger = logging.getLogger(__name__)


async def process_import_parsing(ctx, task_id: int):
    """文档导入解析后台任务"""
    async with AsyncSessionLocal() as db:
        from app.crud.task import crud_task
        from app.services.task_service import TaskService

        task = await crud_task.get(db, id=task_id)
        if not task:
            logger.error(f"❌ 任务 {task_id} 不存在")
            return

        try:
            await TaskService.update_progress(db, task_id, 10.0)
            payload = task.payload

            # 1. 准备解析器
            from app.core.doc_processor import DocProcessorFactory
            from app.crud.document import crud_document
            from app.models.document import DocumentStatus
            from app.schemas.document import DocumentCreate
            from app.schemas.system_config import DocProcessorConfig

            processor_config_dict = payload.get("processor_config")
            processor_config_obj = DocProcessorConfig(**processor_config_dict)
            processor = DocProcessorFactory.create(processor_config_obj)

            # 2. 执行解析
            file_path = Path(payload.get("file_path"))
            logger.info(
                f"⏳ 正在解析文档: {payload.get('filename')} 使用 {processor_config_obj.type}"
            )

            await TaskService.update_progress(db, task_id, 30.0)
            result = await processor.process(file_path)
            await TaskService.update_progress(db, task_id, 70.0)

            # 3. 创建文档记录 (带上租户 ID)
            document_in = DocumentCreate(
                title=payload.get("filename").replace(file_path.suffix, ""),
                content=result.markdown,
                site_id=payload.get("site_id"),
                tenant_id=payload.get("tenant_id"),
                collection_id=payload.get("collection_id"),
                author=payload.get("author"),
                status=DocumentStatus.DRAFT,
            )

            # 使用手动事务控制，避免与前面的 progress commit 冲突
            try:
                document = await crud_document.create(db, obj_in=document_in, auto_commit=False)
                from app.crud.site import crud_site

                await crud_site.increment_article_count(
                    db, site_id=payload.get("site_id"), auto_commit=False
                )

                # 同步设置向量化状态为 PENDING，确保 UI 反映队列状态
                from app.models.document import VectorStatus

                await crud_document.update_vector_status(
                    db, document_id=document.id, status=VectorStatus.PENDING, auto_commit=False
                )
                await db.commit()
                await db.refresh(document)
            except Exception as e:
                await db.rollback()
                logger.error(f"❌ 创建文档记录失败: {e}")
                raise e

            # 自动触发向量化 (可选，根据业务需求，通常导入后都需要学习)
            from app.models.task import TaskType

            await TaskService.enqueue_task(
                db,
                task_type=TaskType.VECTORIZE,
                tenant_id=payload.get("tenant_id"),
                site_id=payload.get("site_id"),
                created_by=payload.get("author"),
                payload={"document_id": document.id},
            )

            await TaskService.complete(
                db,
                task_id,
                result={
                    "msg": "解析成功并已加入学习队列",
                    "document_id": document.id,
                    "title": document.title,
                },
            )
            logger.info(f"✅ 任务 {task_id} 处理完成，文档 ID: {document.id}，已自动排队向量化")

        except Exception as e:
            logger.error(f"❌ 任务 {task_id} 失败: {e}", exc_info=True)
            await TaskService.fail(db, task_id, str(e))
        finally:
            # 4. 确保清理持久保存的本地文件
            try:
                file_path = Path(task.payload.get("file_path"))
                if file_path.exists():
                    file_path.unlink()
                    logger.debug(f"🗑️ 已清理任务文件: {file_path}")
            except Exception as e:
                logger.warning(f"⚠️ 清理任务文件失败: {e}")


async def process_vectorize(ctx, task_id: int):
    """文档向量化后台任务"""
    async with AsyncSessionLocal() as db:
        from app.crud.task import crud_task
        from app.services.task_service import TaskService

        task = await crud_task.get(db, id=task_id)
        if not task:
            return

        try:
            await TaskService.update_progress(db, task_id, 10.0)
            doc_id = task.payload.get("document_id")

            # 调用原本的向量化逻辑
            from app.services.document_service import DocumentService
            # 注意：此处需要处理 DocumentService 的实例化，或者将其向量化方法改为静态/类方法
            # 现有的 process_vectorization_task 已经是静态方法了

            logger.info(f"🔄 正在向量化文档: {doc_id} (TaskID: {task_id})")
            await DocumentService.process_vectorization_task(doc_id)

            await TaskService.complete(db, task_id, result={"msg": "向量化完成"})

        except Exception as e:
            logger.error(f"❌ 任务 {task_id} 失败: {e}", exc_info=True)
            await TaskService.fail(db, task_id, str(e))
