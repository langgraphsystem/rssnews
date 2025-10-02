"""
Integration test for Memory Store with Railway database
"""
import asyncio
import os
import pytest
from core.memory.memory_store import create_memory_store
from core.memory.embeddings_service import create_embeddings_service


@pytest.mark.asyncio
async def test_memory_store_full_cycle():
    """Test full memory cycle: store → recall → delete"""

    # Setup
    embeddings_service = create_embeddings_service(provider="openai")
    memory_store = create_memory_store(embeddings_service)

    # Test 1: Store episodic memory
    print("\n📝 Test 1: Storing episodic memory...")
    memory_id = await memory_store.store(
        content="AI breakthrough: GPT-5 achieves 95% on reasoning benchmarks",
        memory_type="episodic",
        importance=0.9,
        ttl_days=90,
        refs=["article-123"],
        user_id="test_user"
    )
    print(f"✅ Stored memory: {memory_id}")

    # Test 2: Store semantic memory
    print("\n📝 Test 2: Storing semantic memory...")
    semantic_id = await memory_store.store(
        content="Machine learning models improve through training on large datasets",
        memory_type="semantic",
        importance=0.7,
        ttl_days=180,
        refs=["wiki-ml"],
        user_id="test_user"
    )
    print(f"✅ Stored semantic memory: {semantic_id}")

    # Test 3: Recall by semantic search
    print("\n🔍 Test 3: Semantic search...")
    results = await memory_store.recall(
        query="artificial intelligence breakthroughs",
        user_id="test_user",
        limit=5,
        min_similarity=0.3
    )
    print(f"✅ Found {len(results)} memories:")
    for i, mem in enumerate(results, 1):
        print(f"  {i}. [{mem['type']}] {mem['content'][:60]}... (similarity: {mem.get('similarity', 0):.3f})")

    # Test 4: Get by ID
    print("\n🔍 Test 4: Get by ID...")
    retrieved = await memory_store.get_by_id(memory_id)
    assert retrieved is not None
    assert retrieved["content"] == "AI breakthrough: GPT-5 achieves 95% on reasoning benchmarks"
    print(f"✅ Retrieved memory by ID: {retrieved['id']}")

    # Test 5: Suggest storage
    print("\n💡 Test 5: Suggest storage...")
    docs = [
        {"title": "Breaking: New quantum computer breaks encryption", "score": 0.95, "date": "2025-10-01"},
        {"title": "Weather forecast: Sunny tomorrow", "score": 0.3},
        {"title": "Machine learning advances in healthcare", "score": 0.85}
    ]
    suggestions = await memory_store.suggest_storage(docs, max_suggestions=3)
    print(f"✅ Got {len(suggestions)} suggestions:")
    for i, sugg in enumerate(suggestions, 1):
        print(f"  {i}. [{sugg['type']}] {sugg['content'][:50]}... (importance: {sugg['importance']:.2f})")

    # Test 6: Cleanup
    print("\n🗑️  Test 6: Cleanup...")
    deleted = await memory_store.delete(memory_id)
    assert deleted is True
    deleted2 = await memory_store.delete(semantic_id)
    assert deleted2 is True
    print(f"✅ Deleted test memories")

    # Verify deletion
    retrieved_after = await memory_store.get_by_id(memory_id)
    assert retrieved_after is None or retrieved_after.get("deleted_at") is not None
    print(f"✅ Verified soft delete")

    print("\n🎉 All tests passed!")


@pytest.mark.asyncio
async def test_memory_analytics():
    """Test memory analytics"""
    embeddings_service = create_embeddings_service(provider="openai")
    memory_store = create_memory_store(embeddings_service)

    print("\n📊 Testing analytics...")

    # Store some test data
    ids = []
    for i in range(3):
        mem_id = await memory_store.store(
            content=f"Test memory {i} for analytics",
            memory_type="semantic" if i % 2 == 0 else "episodic",
            importance=0.5 + (i * 0.1),
            ttl_days=90,
            user_id="analytics_test"
        )
        ids.append(mem_id)

    # Get analytics
    stats = await memory_store.get_analytics(user_id="analytics_test")
    print(f"✅ Analytics: {stats}")

    assert stats["total"] >= 3
    assert stats["by_type"]["semantic"] >= 2
    assert stats["by_type"]["episodic"] >= 1

    # Cleanup
    for mem_id in ids:
        await memory_store.delete(mem_id)

    print("✅ Analytics test passed!")


if __name__ == "__main__":
    print("=" * 60)
    print("Memory Store Integration Test")
    print("=" * 60)

    # Check environment
    if not os.getenv("PG_DSN"):
        print("❌ Error: PG_DSN environment variable not set")
        exit(1)

    if not os.getenv("OPENAI_API_KEY"):
        print("❌ Error: OPENAI_API_KEY environment variable not set")
        exit(1)

    print("✅ Environment variables configured")

    # Run tests
    asyncio.run(test_memory_store_full_cycle())
    print("\n" + "=" * 60 + "\n")
    asyncio.run(test_memory_analytics())

    print("\n" + "=" * 60)
    print("✅ All integration tests passed!")
    print("=" * 60)
