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

"""向量存储管理器

使用 langchain-postgres 最佳实践实现
"""

import asyncio
import logging
import time
from typing import Any, Optional
from urllib.parse import quote_plus

from langchain_core.documents import Document as LangChainDocument
from langchain_postgres import PGEngine, PGVectorStore
from langchain_postgres.v2.engine import Column
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.common.utils import log_ai_usage_signal
from app.core.infra.config import settings

logger = logging.getLogger(__name__)

# 元数据列定义（同时用于表初始化和 PGVectorStore 实例创建）
METADATA_COLUMNS = [
    Column(name="source", data_type="TEXT", nullable=True),
    Column(name="id", data_type="TEXT", nullable=True),
    Column(name="site_id", data_type="INTEGER", nullable=True),
    Column(name="collection_id", data_type="INTEGER", nullable=True),
    Column(name="tenant_id", data_type="INTEGER", nullable=True),
]

# 优化查询的顶层物理列名（与 METADATA_COLUMNS 保持一致）
OPTIMIZED_COLUMN_NAMES = [col.name for col in METADATA_COLUMNS]


class VectorStoreManager:
    """向量存储管理器（单例模式）

    基于 langchain-postgres 文档最佳实践：
    - 使用 PGEngine.from_engine() 管理连接池
    - 使用 ainit_vectorstore_table() 初始化表
    - 使用 PGVectorStore.create() 创建向量存储

    锁策略（Double-check locking）：
    - 快速路径（无锁）：配置哈希命中缓存 → 切换指针 → 直接返回
    - 慢速路径（持锁）：创建新 Embeddings/PGVectorStore 实例、Schema 迁移
    """

    _instance: Optional["VectorStoreManager"] = None
    _lock = asyncio.Lock()

    def __init__(self, collection_name: str = "catwiki_documents"):
        self.collection_name = collection_name
        self._sa_engine = None  # 底层 SQLAlchemy 异步引擎 (进程内共享)
        self._engine: PGEngine | None = None  # PGEngine (进程内共享)

        # 核心缓存：基于配置哈希，实现多租户/多模型配置的实例隔离
        self._vector_stores: dict[str, PGVectorStore] = {}  # hash → PGVectorStore
        self._embeddings_cache: dict[str, Any] = {}  # hash → Embeddings

        # 当前上下文选中的实例 (由 _ensure_initialized 动态指向)
        self._current_store: PGVectorStore | None = None
        self._current_embeddings = None
        self._current_model: str | None = None
        self._current_hash: str | None = None

    # ==================== 初始化与配置 ====================

    async def _resolve_config(self, tenant_id: int | None = None):
        """解析当前租户的 embedding 配置（无锁，可安全在锁外调用）"""
        from app.core.infra.config_resolver import ConfigResolver
        from app.core.infra.tenant import get_current_tenant

        if tenant_id is None:
            tenant_id = get_current_tenant()

        embedding_conf = await ConfigResolver.resolve_section("embedding", tenant_id=tenant_id)

        api_key = embedding_conf.get("api_key")
        mode = embedding_conf.get("_mode", "platform")

        if not api_key:
            if mode == "custom":
                from app.core.web.exceptions import BadRequestException

                raise BadRequestException("已开启自定义向量化模式，但未配置 API Key。")
            raise ValueError(
                f"未找到有效的 Embedding 配置 (租户: {tenant_id}, 模式: {mode})，请检查 AI 模型配置。"
            )

        return tenant_id, embedding_conf

    def _try_cache_hit(
        self,
        conf_hash: str,
        model: str,
        tenant_id: int | None,
        embedding_conf: dict | None = None,
        purpose: str | None = None,
    ) -> bool:
        """尝试命中缓存（无锁快速路径），命中则更新 current 指针"""
        if conf_hash not in self._vector_stores:
            return False

        extra = None
        if embedding_conf:
            extra = {
                "Provider": embedding_conf.get("provider", "N/A"),
                "Base URL": embedding_conf.get("base_url", "N/A"),
                "Dimension": embedding_conf.get("dimension", "auto"),
                "Source": embedding_conf.get("_source", "platform"),
            }
        log_ai_usage_signal(
            "embedding",
            model,
            conf_hash,
            is_hit=True,
            tenant_id=tenant_id,
            extra=extra,
            purpose=purpose,
        )
        self._current_store = self._vector_stores[conf_hash]
        self._current_embeddings = self._embeddings_cache[conf_hash]
        self._current_model = model
        self._current_hash = conf_hash
        return True

    async def _ensure_initialized(
        self, tenant_id: int | None = None, force: bool = False, purpose: str | None = None
    ):
        """确保向量存储已初始化（支持多实例池）"""
        # 1. 解析配置（无锁）
        tenant_id, embedding_conf = await self._resolve_config(tenant_id)
        model = embedding_conf.get("model")
        conf_hash = embedding_conf.get("_hash")

        # 2. 快速路径：缓存命中直接返回（无锁）
        if not force and self._try_cache_hit(
            conf_hash, model, tenant_id, embedding_conf, purpose=purpose
        ):
            return

        # 3. 慢速路径：持锁初始化新实例
        async with self._lock:
            # Double-check：避免并发重复初始化
            if not force and self._try_cache_hit(
                conf_hash, model, tenant_id, embedding_conf, purpose=purpose
            ):
                return
            await self._do_initialize(tenant_id, embedding_conf, purpose=purpose)

    async def _do_initialize(
        self, tenant_id: int | None, embedding_conf: dict, purpose: str | None = None
    ):
        """执行实际的初始化逻辑（调用方必须持有 self._lock）"""
        model = embedding_conf.get("model")
        api_key = embedding_conf.get("api_key")
        base_url = embedding_conf.get("base_url")
        dimension = int(embedding_conf.get("dimension") or 1024)
        source = embedding_conf.get("_source", "platform")
        conf_hash = embedding_conf.get("_hash")

        log_ai_usage_signal(
            "embedding",
            model,
            conf_hash,
            is_hit=False,
            tenant_id=tenant_id,
            extra={
                "Provider": embedding_conf.get("provider"),
                "Base URL": base_url,
                "Dimension": dimension,
                "Source": source,
            },
            purpose=purpose,
        )

        # 初始化 Embeddings
        from app.core.ai.providers.embeddings import OpenAICompatibleEmbeddings

        new_embeddings = OpenAICompatibleEmbeddings(
            model=model,
            api_key=api_key,
            base_url=base_url,
            embedding_batch_size=settings.AI_EMBEDDING_BATCH_SIZE,
            extra_body=embedding_conf.get("extra_body"),
        )

        # 初始化 SQL Engine (单例共享，跨租户复用连接池)
        if self._sa_engine is None:
            self._init_engine()

        # 表初始化 + Schema 迁移
        await self._ensure_table(dimension)
        await self._check_database_dimension(dimension)
        await self._ensure_columns()
        await self._ensure_indexes()

        # 创建 PGVectorStore 实例并存入缓存
        new_store = await PGVectorStore.create(
            engine=self._engine,
            table_name=self.collection_name,
            embedding_service=new_embeddings,
            metadata_columns=OPTIMIZED_COLUMN_NAMES,
        )

        # 存入实例池并切换指针
        self._vector_stores[conf_hash] = new_store
        self._embeddings_cache[conf_hash] = new_embeddings
        self._current_store = new_store
        self._current_embeddings = new_embeddings
        self._current_model = model
        self._current_hash = conf_hash

        logger.debug(
            f"✅ [VectorStore] 实例初始化完成 (哈希: {conf_hash[:8]}, 租户: {tenant_id}, 来源: {source})"
        )

    def _init_engine(self):
        """初始化 SQLAlchemy 引擎（仅首次调用时执行）"""
        encoded_user = quote_plus(settings.POSTGRES_USER)
        encoded_password = quote_plus(settings.POSTGRES_PASSWORD)
        async_conn_str = (
            f"postgresql+asyncpg://{encoded_user}:{encoded_password}"
            f"@{settings.POSTGRES_SERVER}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
        )
        self._sa_engine = create_async_engine(
            async_conn_str,
            pool_size=settings.DB_POOL_SIZE,
            max_overflow=settings.DB_MAX_OVERFLOW,
            pool_timeout=settings.DB_POOL_TIMEOUT,
            pool_recycle=settings.DB_POOL_RECYCLE,
            pool_pre_ping=True,
            pool_reset_on_return="commit",
            echo=False,
            future=True,
        )
        self._engine = PGEngine.from_engine(engine=self._sa_engine)

    async def _ensure_table(self, dimension: int):
        """确保向量存储表存在（仅在第一次物理访问时创建）"""
        try:
            check_sql = text("SELECT 1 FROM information_schema.tables WHERE table_name = :table")
            async with self._sa_engine.connect() as conn:
                result = await conn.execute(check_sql, {"table": self.collection_name})
                if result.fetchone() is not None:
                    return  # 表已存在

            logger.info(f"✨ 创建向量存储表: {self.collection_name} (维度: {dimension})")
            await self._engine.ainit_vectorstore_table(
                table_name=self.collection_name,
                vector_size=dimension,
                metadata_columns=METADATA_COLUMNS,
            )
        except Exception as e:
            if "already exists" not in str(e) and "DuplicateTable" not in str(e):
                raise

    async def reload_credentials(self, tenant_id: int | None = None) -> None:
        """热更新向量存储凭证（强制刷新配置变更）"""
        await self._ensure_initialized(tenant_id=tenant_id, force=True)

    @classmethod
    async def get_instance(cls, purpose: str | None = None) -> "VectorStoreManager":
        """获取向量存储管理器单例（自动感知当前租户上下文）"""
        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()

        # 内部有快速路径，缓存命中时不需要锁
        await cls._instance._ensure_initialized(purpose=purpose)
        return cls._instance

    # ==================== 文档操作 ====================

    async def add_documents(
        self, documents: list[LangChainDocument], ids: list[str], storage_batch_size: int = 100
    ) -> list[str]:
        """添加文档到向量存储

        Args:
            documents: 要存储的文档列表
            ids: 文档 ID 列表
            storage_batch_size: 每批写入数据库的文档数量
        """
        await self._ensure_initialized()

        start_time = time.time()
        total = len(documents)

        for i in range(0, total, storage_batch_size):
            batch_docs = documents[i : i + storage_batch_size]
            batch_ids = ids[i : i + storage_batch_size]
            await self._current_store.aadd_documents(documents=batch_docs, ids=batch_ids)
            logger.debug(
                f"已存储批次 {i // storage_batch_size + 1}/{(total + storage_batch_size - 1) // storage_batch_size}"
            )

        logger.info(
            f"✅ [VectorStore] 已存储 {total} 个文档 | 耗时: {time.time() - start_time:.3f}s"
        )
        return ids

    async def delete_documents(self, ids: list[str]) -> None:
        """从向量存储删除文档"""
        await self._ensure_initialized()
        logger.info(f"开始删除 {len(ids)} 个文档")
        await self._current_store.adelete(ids=ids)
        logger.info("✅ 成功删除文档")

    async def delete_by_metadata(self, key: str, value: str) -> None:
        """根据元数据删除文档"""
        await self._ensure_initialized()
        logger.info(f"开始根据元数据删除文档: {key}={value}")

        where_clause = self._get_metadata_where_clause(key)
        sql = text(f"DELETE FROM {self.collection_name} WHERE {where_clause}")

        async with self._sa_engine.connect() as conn:
            await conn.execute(sql, {"value": value})
            await conn.commit()

        logger.info(f"✅ 成功删除元数据 {key}={value} 的相关向量")

    # ==================== 搜索 ====================

    async def similarity_search(
        self, query: str, k: int = 5, filter: dict | None = None, purpose: str | None = None
    ) -> list[LangChainDocument]:
        """相似度搜索"""
        await self._ensure_initialized(purpose=purpose)
        logger.debug(
            f"♻️  [EMBEDDING] Searching | Model: {self._current_model} | Hash: {self._current_hash[:8] if self._current_hash else 'N/A'}"
        )
        results = await self._current_store.asimilarity_search(query=query, k=k, filter=filter)
        logger.info(f"✨ [EMBEDDING] Found {len(results)} chunks")
        return results

    async def similarity_search_with_score(
        self, query: str, k: int = 5, filter: dict | None = None, purpose: str | None = None
    ) -> list[tuple[LangChainDocument, float]]:
        """带相似度分数的搜索"""
        await self._ensure_initialized(purpose=purpose)
        logger.debug(
            f"♻️  [EMBEDDING] Searching (w/score) | Model: {self._current_model} | Hash: {self._current_hash[:8] if self._current_hash else 'N/A'}"
        )
        return await self._current_store.asimilarity_search_with_score(
            query=query, k=k, filter=filter
        )

    async def get_chunks_by_metadata(self, key: str, value: str) -> list[dict]:
        """根据元数据获取文档片段"""
        await self._ensure_initialized()
        try:
            where_clause = self._get_metadata_where_clause(key)
            sql = text(f"""
                SELECT langchain_id, content, langchain_metadata
                FROM {self.collection_name}
                WHERE {where_clause}
                ORDER BY (langchain_metadata->>'chunk_index')::int ASC
            """)

            async with self._sa_engine.connect() as conn:
                result = await conn.execute(sql, {"value": value})
                rows = result.fetchall()

            return [
                {
                    "id": str(row.langchain_id),
                    "content": row.content,
                    "metadata": row.langchain_metadata,
                }
                for row in rows
            ]
        except Exception as e:
            logger.error(f"获取文档片段失败: {e}", exc_info=True)
            return []

    # ==================== 数据库维护 ====================

    def _get_metadata_where_clause(self, key: str) -> str:
        """生成元数据查询条件的 WHERE 子句"""
        if key in OPTIMIZED_COLUMN_NAMES:
            return f"{key} = :value"
        return f"langchain_metadata->>'{key}' = :value"

    async def _check_database_dimension(self, expected_dim: int):
        """检查数据库中的向量维度是否与配置匹配"""
        try:
            sql = text(
                "SELECT format_type(atttypid, atttypmod) as type_def "
                "FROM pg_attribute "
                "WHERE attrelid = CAST(:table AS regclass) AND attname = 'embedding'"
            )
            async with self._sa_engine.connect() as conn:
                result = await conn.execute(sql, {"table": self.collection_name})
                row = result.fetchone()

            if not row or not row.type_def or "vector(" not in row.type_def:
                return

            # 提取维度：e.g., "vector(1024)" → 1024
            actual_dim = int(row.type_def.split("(")[1].split(")")[0])

            if actual_dim != expected_dim:
                error_msg = (
                    f"CRITICAL: Database vector dimension mismatch! "
                    f"DB Table '{self.collection_name}' has dimension {actual_dim}, "
                    f"but configuration requires {expected_dim}. "
                    f"Please DROP the table to reset: 'DROP TABLE {self.collection_name};'"
                )
                logger.critical(error_msg)
                raise ValueError(error_msg)

            logger.debug(f"✅ [VectorStore] Dimension check passed: {actual_dim}")

        except ValueError:
            raise  # 维度不匹配的 ValueError 必须向上抛出
        except Exception as e:
            if "does not exist" in str(e):
                return  # 表不存在，可忽略
            raise

    async def _ensure_columns(self):
        """确保所有优化列在数据库表中存在（Schema Evolution）"""
        try:
            target_columns = ["collection_id", "tenant_id"]

            async with self._sa_engine.connect() as conn:
                conn = await conn.execution_options(isolation_level="AUTOCOMMIT")

                result = await conn.execute(
                    text(
                        f"SELECT column_name FROM information_schema.columns WHERE table_name = '{self.collection_name}'"
                    )
                )
                existing_columns = {row[0] for row in result.fetchall()}

                for col in target_columns:
                    if col not in existing_columns:
                        logger.info(f"🔄 [Schema] 检测到缺少列 '{col}'，正在添加...")
                        await conn.execute(
                            text(f"ALTER TABLE {self.collection_name} ADD COLUMN {col} INTEGER")
                        )
                        logger.info(f"✅ [Schema] 成功添加列 '{col}'")

        except Exception as e:
            logger.error(f"❌ [Schema] 列检查/迁移失败: {e}", exc_info=True)

    async def _ensure_indexes(self):
        """确保关键查询字段拥有索引"""
        try:
            target_indexes = ["id", "site_id", "collection_id", "tenant_id"]

            async with self._sa_engine.connect() as conn:
                conn = await conn.execution_options(isolation_level="AUTOCOMMIT")

                result = await conn.execute(
                    text(
                        f"SELECT indexname FROM pg_indexes WHERE tablename = '{self.collection_name}'"
                    )
                )
                existing_indexes = {row[0] for row in result.fetchall()}

                for col in target_indexes:
                    index_name = f"idx_{self.collection_name}_{col}"
                    if index_name not in existing_indexes:
                        logger.info(f"🔄 [Index] 检测到缺少索引 '{index_name}'，正在创建...")
                        await conn.execute(
                            text(
                                f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {index_name} ON {self.collection_name} ({col})"
                            )
                        )
                        logger.info(f"✅ [Index] 成功创建索引 '{index_name}'")

        except Exception as e:
            logger.warning(f"⚠️ [Index] 索引维护失败 (可能是权限不足或已存在): {e}")

    # ==================== 生命周期 ====================

    async def close(self):
        """关闭数据库连接"""
        if self._sa_engine:
            await self._sa_engine.dispose()
            logger.info("✅ 向量存储连接已关闭")
