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

"""健康检查服务"""

import logging
from datetime import UTC, datetime

from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.infra.config import settings
from app.core.infra.rustfs import get_rustfs_service
from app.db.database import get_db


class HealthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_health_status(self, detailed: bool = False) -> dict:
        """获取系统健康状态

        Args:
            detailed: 是否进行详细检查（包含对象存储等）
        """
        logger = logging.getLogger(__name__)

        try:
            from app.ee.license import license_service

            is_licensed = license_service.is_valid
        except ImportError:
            is_licensed = False

        status = "healthy"
        checks = {}

        # 1. 检查数据库
        try:
            await self.db.execute(text("SELECT 1"))
            checks["database"] = "ok"
        except Exception as e:
            checks["database"] = f"error: {str(e)}"
            status = "unhealthy"
            logger.error(f"健康检查: 数据库连接失败 - {e}")

        # 2. 检查缓存
        try:
            from app.core.infra.cache import get_cache

            cache = get_cache()
            stats = cache.stats()
            # 获取后端名称 (如 redis 或 memory)
            backend_type = stats.get("backend", "unknown")
            checks["cache"] = backend_type
        except Exception as e:
            checks["cache"] = f"error: {str(e)}"
            if status == "healthy":
                status = "degraded"
            logger.error(f"健康检查: 缓存检查失败 - {e}")

        # 3. 详细检查 (仅在需要时)
        if detailed:
            try:
                rustfs = get_rustfs_service()
                if rustfs.is_available():
                    if rustfs.client.bucket_exists(rustfs.bucket_name):
                        checks["storage"] = "ok"
                    else:
                        checks["storage"] = "warning: bucket not found"
                        if status == "healthy":
                            status = "degraded"
                else:
                    checks["storage"] = "unavailable"
                    if status == "healthy":
                        status = "degraded"
            except Exception as e:
                checks["storage"] = f"error: {str(e)}"
                if status == "healthy":
                    status = "degraded"
                logger.error(f"健康检查: RustFS 检查失败 - {e}")

        return {
            "status": status,
            "version": settings.VERSION,
            "environment": settings.ENVIRONMENT,
            "edition": settings.CATWIKI_EDITION,
            "is_licensed": is_licensed,
            "timestamp": datetime.now(UTC).isoformat(),
            "checks": checks,
        }


def get_health_service(db: AsyncSession = Depends(get_db)) -> HealthService:
    """获取 HealthService 实例的依赖注入函数"""
    return HealthService(db)
