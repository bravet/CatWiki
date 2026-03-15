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

from arq import func

from app.core.queue.redis import redis_settings
from app.worker.document_tasks import process_import_parsing, process_vectorize

logger = logging.getLogger(__name__)


async def startup(ctx):
    logger.info("🚀 Arq Worker 正在启动...")
    # 打印已注册的函数名称，方便调试
    registered_funcs = [
        f if isinstance(f, str) else getattr(f, "name", getattr(f, "__name__", str(f)))
        for f in WorkerSettings.functions
    ]
    logger.info(f"📋 已注册函数: {registered_funcs}")


async def shutdown(ctx):
    logger.info("🛑 Arq Worker 正在关闭...")


class WorkerSettings:
    """Arq Worker 配置"""

    functions = [
        func(process_import_parsing, name="process_import_parsing"),
        func(process_vectorize, name="process_vectorize"),
    ]
    redis_settings = redis_settings
    on_startup = startup
    on_shutdown = shutdown

    # 任务重试次数
    max_tries = 3
    # 任务超时时间 (秒)
    job_timeout = 600  # 10 分钟，考虑到 PDF 解析可能较慢
