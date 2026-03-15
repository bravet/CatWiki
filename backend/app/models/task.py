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

import enum

from sqlalchemy import JSON, Column, Float, Integer, String, Text

from app.models.base import BaseModel


class TaskStatus(str, enum.Enum):
    """任务状态枚举"""

    PENDING = "pending"  # 等待中
    RUNNING = "running"  # 执行中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"  # 失败


class TaskType(str, enum.Enum):
    """任务类型枚举"""

    IMPORT_PARSING = "import_parsing"  # 文档导入解析
    VECTORIZE = "vectorize"  # 向量化处理


class Task(BaseModel):
    """通用后台任务模型"""

    __tablename__ = "task"

    tenant_id = Column(Integer, nullable=False, index=True, comment="所属租户ID")
    site_id = Column(Integer, nullable=True, index=True, comment="所属站点ID")
    task_type = Column(String(50), nullable=False, index=True, comment="任务类型")
    status = Column(
        String(20), default=TaskStatus.PENDING.value, nullable=False, index=True, comment="任务状态"
    )

    job_id = Column(String(100), nullable=True, index=True, comment="Arq Job ID")

    progress = Column(Float, default=0.0, nullable=False, comment="进度 (0.0 - 100.0)")

    # 任务参数和结果 (使用 JSON 存储)
    payload = Column(JSON, nullable=True, comment="任务参数")
    result = Column(JSON, nullable=True, comment="执行结果")
    error = Column(Text, nullable=True, comment="错误信息")

    created_by = Column(String(100), nullable=False, comment="创建者")

    def __repr__(self) -> str:
        # 使用 __dict__.get() 避免在对象脱离 session 时触发 refresh 导致的 DetachedInstanceError
        return f"<Task(id={self.id}, type='{self.__dict__.get('task_type')}', status='{self.__dict__.get('status')}')>"
