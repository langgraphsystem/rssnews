#!/usr/bin/env python3
"""Test search via direct SQL to verify data"""
import os
from dotenv import load_dotenv
load_dotenv()

from pg_client_new import PgClient
from openai_embedding_generator import OpenAIEmbeddingGenerator
import asyncio

async def test_search_sql():
    db = PgClient()
    gen = OpenAIEmbeddingGenerator()

    print("=" * 80)
    print("🔍 SQL-based Search Test")
    print("=" * 80)
    print()

    # Test query
    query = "Trump election"
    print(f"Query: '{query}'")
    print()

    # Generate query embedding
    print("🔮 Generating query embedding...")
    embeddings = await gen.generate_embeddings([query])
    query_embedding = embeddings[0]

    if not query_embedding:
        print("❌ Failed to generate embedding")
        return False

    print(f"✅ Query embedding generated ({len(query_embedding)} dims)")
    print()

    # Search via direct SQL
    print("🔍 Searching via pgvector...")

    with db._cursor() as cur:
        # Semantic search using <=> (cosine distance)
        cur.execute("""
            SELECT
                title_norm,
                source_domain,
                published_at,
                1 - (embedding <=> %s::vector) as similarity
            FROM article_chunks
            WHERE embedding IS NOT NULL
            ORDER BY embedding <=> %s::vector
            LIMIT 10
        """, (query_embedding, query_embedding))

        results = cur.fetchall()

        if results:
            print(f"✅ Found {len(results)} results\n")
            print("📰 Top Results:")
            print()
            for i, (title, source, published, similarity) in enumerate(results, 1):
                print(f"{i}. [{similarity:.4f}] {title[:70]}...")
                print(f"   Source: {source} | Published: {published}")
                print()
        else:
            print("❌ No results found")
            return False

    print("=" * 80)
    print("✅ Search test passed!")
    return True

if __name__ == "__main__":
    success = asyncio.run(test_search_sql())
    exit(0 if success else 1)
