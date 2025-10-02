"""
Memory Store — Database interface for long-term memory storage and retrieval.
Supports semantic search via vector embeddings.
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
try:
    import asyncpg
except ImportError:  # pragma: no cover - optional dependency
    asyncpg = None

from core.memory.embeddings_service import EmbeddingsService, create_embeddings_service

logger = logging.getLogger(__name__)


class MemoryStore:
    """
    Database interface for memory storage with semantic search.
    Requires PostgreSQL with pgvector extension.
    """

    def __init__(
        self,
        db_dsn: str,
        embeddings_service
    ):
        """
        Initialize memory store

        Args:
            db_dsn: PostgreSQL connection string
            embeddings_service: EmbeddingsService instance
        """
        self.db_dsn = db_dsn
        self.db_pool = None  # Lazy initialization
        self.embeddings_service = embeddings_service

    async def _ensure_pool(self):
        """Ensure database connection pool exists"""
        if self.db_pool is None:
            if asyncpg is None:
                raise RuntimeError("asyncpg not installed")
            self.db_pool = await asyncpg.create_pool(
                dsn=self.db_dsn,
                min_size=2,
                max_size=10
            )
            logger.info("Memory store connection pool created")

    async def store(
        self,
        content: str,
        memory_type: str,
        importance: float = 0.5,
        ttl_days: int = 90,
        refs: Optional[List[str]] = None,
        user_id: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> str:
        """
        Store a memory record

        Args:
            content: Memory content
            memory_type: Type (episodic or semantic)
            importance: Importance score [0.0, 1.0]
            ttl_days: Time-to-live in days
            refs: List of article IDs or URLs
            user_id: User ID for multi-tenant
            tags: Optional tags for categorization

        Returns:
            Memory ID (UUID)
        """
        await self._ensure_pool()

        # Generate embedding
        embedding = await self.embeddings_service.embed_text(content)

        # Convert embedding to pgvector format
        embedding_str = '[' + ','.join(map(str, embedding)) + ']'

        # Insert into database
        async with self.db_pool.acquire() as conn:
            memory_id = await conn.fetchval(
                """
                INSERT INTO memory_records (
                    type, content, embedding, importance, ttl_days,
                    refs, user_id, tags
                )
                VALUES ($1, $2, $3::vector, $4, $5, $6, $7, $8)
                RETURNING id
                """,
                memory_type,
                content,
                embedding_str,
                importance,
                ttl_days,
                refs or [],
                user_id,
                tags or []
            )

        logger.info(
            f"Stored memory: id={memory_id}, type={memory_type}, "
            f"importance={importance:.2f}, ttl={ttl_days}d"
        )

        return str(memory_id)

    async def recall(
        self,
        query: str,
        user_id: Optional[str] = None,
        memory_type: Optional[str] = None,
        limit: int = 10,
        min_similarity: float = 0.5
    ) -> List[Dict[str, Any]]:
        """
        Recall memories via semantic search

        Args:
            query: Search query
            user_id: Filter by user ID
            memory_type: Filter by type (episodic or semantic)
            limit: Maximum number of results
            min_similarity: Minimum similarity threshold

        Returns:
            List of memory records with similarity scores
        """
        await self._ensure_pool()

        # Generate query embedding
        query_embedding = await self.embeddings_service.embed_text(query)

        # Convert to pgvector format
        query_embedding_str = '[' + ','.join(map(str, query_embedding)) + ']'

        # Build SQL query
        sql = """
            SELECT
                id,
                type,
                content,
                importance,
                ttl_days,
                refs,
                created_at,
                expires_at,
                last_accessed_at,
                access_count,
                tags,
                1 - (embedding <=> $1::vector) as similarity
            FROM active_memory_records
            WHERE 1=1
        """

        params = [query_embedding_str]
        param_idx = 2

        # Add filters
        if user_id:
            sql += f" AND user_id = ${param_idx}"
            params.append(user_id)
            param_idx += 1

        if memory_type:
            sql += f" AND type = ${param_idx}"
            params.append(memory_type)
            param_idx += 1

        # Add similarity threshold
        sql += f" AND (1 - (embedding <=> $1::vector)) >= ${param_idx}"
        params.append(min_similarity)
        param_idx += 1

        # Order and limit
        sql += f" ORDER BY embedding <=> $1::vector LIMIT ${param_idx}"
        params.append(limit)

        # Execute query
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)

            # Update access tracking for retrieved memories
            memory_ids = [row["id"] for row in rows]
            if memory_ids:
                await conn.execute(
                    """
                    UPDATE memory_records
                    SET last_accessed_at = NOW(),
                        access_count = access_count + 1
                    WHERE id = ANY($1::uuid[])
                    """,
                    memory_ids
                )

                # Log access
                await conn.executemany(
                    """
                    INSERT INTO memory_access_log (memory_id, query_text, similarity_score, user_id)
                    VALUES ($1, $2, $3, $4)
                    """,
                    [
                        (row["id"], query, row["similarity"], user_id)
                        for row in rows
                    ]
                )

        memories = [dict(row) for row in rows]

        logger.info(
            f"Recalled {len(memories)} memories for query '{query[:50]}...' "
            f"(min_similarity={min_similarity:.2f})"
        )

        return memories

    async def get_by_id(self, memory_id: str) -> Optional[Dict[str, Any]]:
        """
        Get memory by ID

        Args:
            memory_id: Memory UUID

        Returns:
            Memory record or None if not found
        """
        await self._ensure_pool()

        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    id, type, content, importance, ttl_days, refs,
                    created_at, expires_at, last_accessed_at, access_count,
                    user_id, tags
                FROM memory_records
                WHERE id = $1 AND deleted_at IS NULL
                """,
                uuid.UUID(memory_id)
            )

        if row:
            return dict(row)
        return None

    async def delete(self, memory_id: str, soft: bool = True) -> bool:
        """
        Delete a memory record

        Args:
            memory_id: Memory UUID
            soft: If True, soft delete (set deleted_at). If False, hard delete.

        Returns:
            True if deleted, False if not found
        """
        await self._ensure_pool()

        async with self.db_pool.acquire() as conn:
            if soft:
                result = await conn.execute(
                    """
                    UPDATE memory_records
                    SET deleted_at = NOW()
                    WHERE id = $1 AND deleted_at IS NULL
                    """,
                    uuid.UUID(memory_id)
                )
            else:
                result = await conn.execute(
                    """
                    DELETE FROM memory_records
                    WHERE id = $1
                    """,
                    uuid.UUID(memory_id)
                )

        deleted = result.split()[-1] == "1"

        if deleted:
            logger.info(f"Deleted memory: id={memory_id}, soft={soft}")

        return deleted

    async def cleanup_expired(self) -> int:
        """
        Clean up expired memories (soft delete)

        Returns:
            Number of memories cleaned up
        """
        await self._ensure_pool()

        async with self.db_pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE memory_records
                SET deleted_at = NOW()
                WHERE expires_at < NOW()
                  AND deleted_at IS NULL
                """
            )

        count = int(result.split()[-1])

        logger.info(f"Cleaned up {count} expired memories")

        return count

    async def get_stats(
        self,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get memory statistics

        Args:
            user_id: Optional user ID filter

        Returns:
            Statistics dict
        """
        await self._ensure_pool()

        async with self.db_pool.acquire() as conn:
            if user_id:
                row = await conn.fetchrow(
                    """
                    SELECT
                        COUNT(*) as total_records,
                        COUNT(*) FILTER (WHERE expires_at > NOW() AND deleted_at IS NULL) as active_records,
                        COUNT(*) FILTER (WHERE deleted_at IS NOT NULL) as deleted_records,
                        AVG(importance) as avg_importance,
                        AVG(access_count) as avg_access_count,
                        MAX(created_at) as last_created_at
                    FROM memory_records
                    WHERE user_id = $1
                    """,
                    user_id
                )
            else:
                row = await conn.fetchrow(
                    """
                    SELECT
                        COUNT(*) as total_records,
                        COUNT(*) FILTER (WHERE expires_at > NOW() AND deleted_at IS NULL) as active_records,
                        COUNT(*) FILTER (WHERE deleted_at IS NOT NULL) as deleted_records,
                        AVG(importance) as avg_importance,
                        AVG(access_count) as avg_access_count,
                        MAX(created_at) as last_created_at
                    FROM memory_records
                    """
                )

        return dict(row) if row else {}

    async def suggest_storage(
        self,
        content: str,
        user_id: Optional[str] = None,
        min_importance: float = 0.6
    ) -> Dict[str, Any]:
        """
        Suggest whether content should be stored in memory

        Args:
            content: Content to evaluate
            user_id: User ID
            min_importance: Minimum importance threshold

        Returns:
            Suggestion dict with should_store, importance, suggested_type, ttl_days
        """
        # Simple heuristics (can be replaced with ML model)
        importance = 0.5

        # Higher importance for longer, detailed content
        if len(content) > 200:
            importance += 0.1

        # Check for duplicate/similar memories
        similar = await self.recall(
            query=content,
            user_id=user_id,
            limit=1,
            min_similarity=0.9
        )

        if similar:
            # Very similar memory exists, lower importance
            importance -= 0.2

        # Determine type
        # Episodic: event-based, time-specific
        # Semantic: fact-based, timeless
        suggested_type = "semantic"
        if any(word in content.lower() for word in ["today", "yesterday", "this week", "announced", "launched"]):
            suggested_type = "episodic"

        # Determine TTL
        ttl_days = 90 if suggested_type == "semantic" else 30

        should_store = importance >= min_importance

        return {
            "should_store": should_store,
            "importance": round(importance, 2),
            "suggested_type": suggested_type,
            "ttl_days": ttl_days,
            "reason": "High importance content" if should_store else "Low importance or duplicate"
        }


class InMemoryMemoryStore:
    """Lightweight in-memory memory store for testing"""

    def __init__(self, embeddings_service):
        self.embeddings_service = embeddings_service
        self.records: List[Dict[str, Any]] = []

    async def store(
        self,
        content: str,
        memory_type: str,
        importance: float = 0.5,
        ttl_days: int = 90,
        refs: Optional[List[str]] = None,
        user_id: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> str:
        memory_id = str(uuid.uuid4())
        embedding = await self.embeddings_service.embed_text(content)
        now = datetime.utcnow()
        record = {
            "id": memory_id,
            "type": memory_type,
            "content": content,
            "importance": importance,
            "ttl_days": ttl_days,
            "refs": refs or [],
            "user_id": user_id,
            "tags": tags or [],
            "created_at": now,
            "expires_at": now + timedelta(days=ttl_days),
            "embedding": embedding,
        }
        self.records.append(record)
        return memory_id

    async def recall(
        self,
        query: str,
        user_id: Optional[str] = None,
        memory_type: Optional[str] = None,
        limit: int = 10,
        min_similarity: float = 0.5
    ) -> List[Dict[str, Any]]:
        if not self.records:
            return []
        query_embedding = await self.embeddings_service.embed_text(query)
        results = []
        for rec in self.records:
            if user_id and rec.get("user_id") != user_id:
                continue
            if memory_type and rec.get("type") != memory_type:
                continue
            rec_embedding = rec.get("embedding")
            similarity = EmbeddingsService.cosine_similarity(query_embedding, rec_embedding)
            if similarity >= min_similarity:
                enriched = dict(rec)
                enriched["similarity"] = similarity
                results.append(enriched)
        results.sort(key=lambda item: item["similarity"], reverse=True)
        return results[:limit]

    async def suggest_storage(self, docs, max_suggestions: int = 5):
        suggestions = []
        doc_list = docs if isinstance(docs, list) else [docs]
        for doc in doc_list[:max_suggestions]:
            if isinstance(doc, dict):
                content = doc.get("snippet") or doc.get("title") or ""
                importance = float(doc.get("score", 0.6) or 0.6)
                has_date = bool(doc.get("date"))
            else:
                content = str(doc)
                importance = 0.6
                has_date = False
            if not content:
                continue
            importance = round(min(1.0, max(0.4, importance)), 2)
            mem_type = "episodic" if has_date else "semantic"
            ttl_days = 90 if mem_type == "semantic" else 30
            suggestions.append(
                {
                    "content": content,
                    "importance": importance,
                    "type": mem_type,
                    "ttl_days": ttl_days,
                }
            )
        return suggestions


def create_memory_store(
    embeddings_service: EmbeddingsService,
    db_dsn: Optional[str] = None
) -> MemoryStore:
    """
    Factory function to create memory store

    Args:
        embeddings_service: EmbeddingsService instance
        db_dsn: PostgreSQL DSN (defaults to PG_DSN env var)

    Returns:
        MemoryStore instance (pool created on first use)
    """
    import os
    mode = os.getenv("PHASE3_MEMORY_MODE", "").lower()
    db_dsn = db_dsn or os.getenv("PG_DSN")

    if mode == "mock" or not db_dsn or asyncpg is None:
        logger.info("MemoryStore running in mock mode")
        return InMemoryMemoryStore(embeddings_service)

    return MemoryStore(db_dsn=db_dsn, embeddings_service=embeddings_service)
