"""
Integration tests for Phase 3 Memory System
"""

import os
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, patch

# Skip if no database configured
pytestmark = pytest.mark.skipif(
    not os.getenv("PG_DSN"),
    reason="PG_DSN not configured"
)


@pytest.fixture
def mock_embeddings():
    """Mock embeddings service"""
    with patch("core.memory.embeddings_service.EmbeddingsService") as mock:
        service = mock.return_value
        # Return fake embedding vector
        service.embed_text = AsyncMock(return_value=[0.1] * 1536)
        yield service


@pytest.mark.asyncio
@pytest.mark.integration
async def test_memory_store_recall_flow(mock_embeddings):
    """Test full store → recall workflow"""
    from core.memory.memory_store import MemoryStore

    db_dsn = os.getenv("PG_DSN")
    store = MemoryStore(db_dsn=db_dsn, embeddings_service=mock_embeddings)

    try:
        # Store a memory
        memory_id = await store.store(
            content="AI adoption is accelerating in enterprise",
            memory_type="semantic",
            importance=0.8,
            ttl_days=90,
            refs=["article_123"],
            user_id="test_user",
            tags=["AI", "enterprise"]
        )

        assert memory_id is not None

        # Recall memories
        results = await store.recall(
            query="AI enterprise trends",
            user_id="test_user",
            top_k=5,
            min_similarity=0.0  # Accept any similarity for test
        )

        assert len(results) > 0

        # Check result structure
        result = results[0]
        assert "id" in result
        assert "content" in result
        assert "similarity" in result
        assert result["user_id"] == "test_user"

    finally:
        # Cleanup: delete test memory
        await store._ensure_pool()
        async with store.db_pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM memory_records WHERE user_id = $1",
                "test_user"
            )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_memory_ttl_expiration(mock_embeddings):
    """Test memory TTL and expiration"""
    from core.memory.memory_store import MemoryStore

    db_dsn = os.getenv("PG_DSN")
    store = MemoryStore(db_dsn=db_dsn, embeddings_service=mock_embeddings)

    try:
        # Store memory with short TTL
        memory_id = await store.store(
            content="Temporary memory",
            memory_type="episodic",
            importance=0.5,
            ttl_days=1,
            user_id="test_user_ttl"
        )

        # Check expires_at is set
        await store._ensure_pool()
        async with store.db_pool.acquire() as conn:
            record = await conn.fetchrow(
                "SELECT expires_at FROM memory_records WHERE id = $1",
                memory_id
            )

            assert record is not None
            assert record["expires_at"] is not None

    finally:
        # Cleanup
        await store._ensure_pool()
        async with store.db_pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM memory_records WHERE user_id = $1",
                "test_user_ttl"
            )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_memory_user_isolation(mock_embeddings):
    """Test that memories are isolated by user_id"""
    from core.memory.memory_store import MemoryStore

    db_dsn = os.getenv("PG_DSN")
    store = MemoryStore(db_dsn=db_dsn, embeddings_service=mock_embeddings)

    try:
        # Store memories for two users
        await store.store(
            content="User 1 memory",
            memory_type="semantic",
            importance=0.8,
            ttl_days=90,
            user_id="test_user_1"
        )

        await store.store(
            content="User 2 memory",
            memory_type="semantic",
            importance=0.8,
            ttl_days=90,
            user_id="test_user_2"
        )

        # Recall for user 1
        results_user1 = await store.recall(
            query="memory",
            user_id="test_user_1",
            top_k=10
        )

        # Recall for user 2
        results_user2 = await store.recall(
            query="memory",
            user_id="test_user_2",
            top_k=10
        )

        # Each user should only see their own memories
        assert all(r["user_id"] == "test_user_1" for r in results_user1)
        assert all(r["user_id"] == "test_user_2" for r in results_user2)

    finally:
        # Cleanup
        await store._ensure_pool()
        async with store.db_pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM memory_records WHERE user_id IN ($1, $2)",
                "test_user_1", "test_user_2"
            )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_memory_tags_filtering(mock_embeddings):
    """Test filtering memories by tags"""
    from core.memory.memory_store import MemoryStore

    db_dsn = os.getenv("PG_DSN")
    store = MemoryStore(db_dsn=db_dsn, embeddings_service=mock_embeddings)

    try:
        # Store memories with different tags
        await store.store(
            content="AI trends memory",
            memory_type="semantic",
            importance=0.8,
            ttl_days=90,
            user_id="test_user_tags",
            tags=["AI", "trends"]
        )

        await store.store(
            content="Crypto news memory",
            memory_type="semantic",
            importance=0.8,
            ttl_days=90,
            user_id="test_user_tags",
            tags=["crypto", "news"]
        )

        # Recall with tag filter
        results = await store.recall(
            query="memory",
            user_id="test_user_tags",
            top_k=10,
            tags=["AI"]
        )

        # Should only get AI-tagged memories
        assert len(results) > 0
        for result in results:
            assert "AI" in result.get("tags", [])

    finally:
        # Cleanup
        await store._ensure_pool()
        async with store.db_pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM memory_records WHERE user_id = $1",
                "test_user_tags"
            )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_memory_importance_filtering(mock_embeddings):
    """Test filtering by importance score"""
    from core.memory.memory_store import MemoryStore

    db_dsn = os.getenv("PG_DSN")
    store = MemoryStore(db_dsn=db_dsn, embeddings_service=mock_embeddings)

    try:
        # Store memories with different importance
        await store.store(
            content="High importance memory",
            memory_type="semantic",
            importance=0.9,
            ttl_days=90,
            user_id="test_user_importance"
        )

        await store.store(
            content="Low importance memory",
            memory_type="semantic",
            importance=0.3,
            ttl_days=90,
            user_id="test_user_importance"
        )

        # Recall with importance filter
        results = await store.recall(
            query="memory",
            user_id="test_user_importance",
            top_k=10,
            min_importance=0.8
        )

        # Should only get high importance memories
        assert len(results) > 0
        for result in results:
            assert result["importance"] >= 0.8

    finally:
        # Cleanup
        await store._ensure_pool()
        async with store.db_pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM memory_records WHERE user_id = $1",
                "test_user_importance"
            )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_memory_suggestions():
    """Test memory suggestion generation"""
    from services.phase3_handlers import execute_memory_command

    # Mock retrieval client
    with patch("core.rag.retrieval_client.get_retrieval_client") as mock_client:
        client = mock_client.return_value
        client.retrieve = AsyncMock(return_value=[
            {
                "article_id": "art_1",
                "title": "AI adoption trends",
                "snippet": "Enterprise AI is growing rapidly",
                "date": "2025-09-30"
            }
        ])

        # Execute memory suggest command
        result = await execute_memory_command(
            operation="suggest",
            query="AI trends",
            window="1w",
            correlation_id="test_suggest"
        )

        assert result is not None
        assert "text" in result


@pytest.mark.asyncio
@pytest.mark.integration
async def test_cleanup_expired_memories(mock_embeddings):
    """Test cleanup of expired memories"""
    from core.memory.memory_store import MemoryStore

    db_dsn = os.getenv("PG_DSN")
    store = MemoryStore(db_dsn=db_dsn, embeddings_service=mock_embeddings)

    try:
        # Store memory with negative TTL (already expired)
        await store._ensure_pool()
        async with store.db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO memory_records (type, content, embedding, importance, ttl_days, user_id, expires_at)
                VALUES ($1, $2, $3::vector, $4, $5, $6, NOW() - INTERVAL '1 day')
                """,
                "semantic",
                "Expired memory",
                '[' + ','.join(['0.1'] * 1536) + ']',
                0.5,
                1,
                "test_user_expired"
            )

        # Run cleanup
        deleted_count = await store.cleanup_expired()

        assert deleted_count >= 1

    finally:
        # Cleanup any remaining test records
        await store._ensure_pool()
        async with store.db_pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM memory_records WHERE user_id = $1",
                "test_user_expired"
            )
