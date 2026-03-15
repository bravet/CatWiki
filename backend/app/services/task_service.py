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

from arq import create_pool
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.queue.redis import redis_settings
from app.crud.task import crud_task
from app.models.task import Task, TaskStatus, TaskType
from app.schemas.task import TaskCreate

logger = logging.getLogger(__name__)


class TaskService:
    """后台任务管理服务"""

    _redis_pool = None

    @classmethod
    async def get_redis_pool(cls):
        if cls._redis_pool is None:
            cls._redis_pool = await create_pool(redis_settings)
        return cls._redis_pool

    @classmethod
    async def enqueue_task(
        cls,
        db: AsyncSession,
        *,
        task_type: TaskType,
        tenant_id: int,
        created_by: str,
        payload: dict,
        site_id: int | None = None,
    ) -> Task:
        """创建一个任务记录并将其推入 Arq 队列"""
        # 1. 创建数据库记录
        task_in = TaskCreate(
            task_type=task_type.value,
            tenant_id=tenant_id,
            site_id=site_id,
            created_by=created_by,
            payload=payload,
            status=TaskStatus.PENDING.value,
            progress=0.0,
        )
        task = await crud_task.create(db, obj_in=task_in)

        # 2. 推入队列
        # Arq 函数名称规范：app.worker.document_tasks.process_document_import (取决于之后具体的实现)
        func_name = f"process_{task_type.value}"

        pool = await cls.get_redis_pool()
        job = await pool.enqueue_job(func_name, task.id)

        # 3. 更新任务记录中的 Job ID
        await crud_task.update(db, db_obj=task, obj_in={"job_id": job.job_id})

        logger.info(f"✅ 任务已推入队列: {task_type} | ID: {task.id} | JobID: {job.job_id}")
        return task

    @classmethod
    async def update_progress(cls, db: AsyncSession, task_id: int, progress: float):
        """更新任务进度"""
        await crud_task.update_status(
            db, task_id=task_id, status=TaskStatus.RUNNING, progress=progress
        )

    @classmethod
    async def complete(cls, db: AsyncSession, task_id: int, result: dict | None = None):
        """标记任务完成"""
        await crud_task.update_status(
            db, task_id=task_id, status=TaskStatus.COMPLETED, progress=100.0, result=result
        )

    @classmethod
    async def fail(cls, db: AsyncSession, task_id: int, error: str):
        """标记任务失败"""
        await crud_task.update_status(db, task_id=task_id, status=TaskStatus.FAILED, error=error)

    @classmethod
    async def close(cls):
        """关闭连接池"""
        if cls._redis_pool is not None:
            await cls._redis_pool.close()
            cls._redis_pool = None
            logger.info("✅ TaskService 队列连接池已关闭")
