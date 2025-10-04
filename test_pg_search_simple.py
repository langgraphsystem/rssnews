#!/usr/bin/env python3
"""Test pg_client search_chunks_by_similarity directly"""
import asyncio
from dotenv import load_dotenv
load_dotenv()

from pg_client_new import PgClient
from openai_embedding_generator import OpenAIEmbeddingGenerator

async def test_pg_search():
    db = PgClient()
    gen = OpenAIEmbeddingGenerator()

    print("Testing search_chunks_by_similarity method...")
    print()

    # Generate embedding
    query = "Trump election"
    embeddings = await gen.generate_embeddings([query])
    query_embedding = embeddings[0]

    print(f"✅ Generated embedding: {len(query_embedding)} dims")
    print()

    # Test with threshold=0.0
    print("🔍 Testing with similarity_threshold=0.0...")
    results = db.search_chunks_by_similarity(
        query_embedding=query_embedding,
        limit=5,
        similarity_threshold=0.0
    )

    print(f"Results: {len(results)}")
    for i, r in enumerate(results[:3]):
        print(f"  {i+1}. [{r.get('similarity', 0):.4f}] {r.get('title_norm', '')[:50]}")

if __name__ == "__main__":
    asyncio.run(test_pg_search())
