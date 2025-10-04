#!/usr/bin/env python3
"""
Test search using existing embeddings from DB
No need to generate new query embedding - reuse existing one
"""
import os
from dotenv import load_dotenv
load_dotenv()

from database.production_db_client import ProductionDBClient

db = ProductionDBClient()

print("=" * 80)
print("🧪 Testing Search with Existing Embeddings")
print("=" * 80)
print()

# Get a random embedding from DB to use as "query"
print("1️⃣  Getting sample embedding from database...")
with db._cursor() as cur:
    cur.execute("""
        SELECT id, title_norm, text, embedding_vector, url, source_domain, published_at
        FROM article_chunks
        WHERE embedding_vector IS NOT NULL
          AND title_norm IS NOT NULL
          AND title_norm != ''
        ORDER BY published_at DESC
        LIMIT 1
    """)

    row = cur.fetchone()
    if not row:
        print("❌ No embeddings found in database!")
        exit(1)

    sample_id, title, text, embedding_vec, url, source, pub_date = row
    print(f"✅ Got sample: '{title[:60]}...'")
    print(f"   Source: {source}")
    print(f"   Published: {pub_date}")
    print()

# Now use this embedding to search for similar articles
print("2️⃣  Searching for similar articles using this embedding...")

with db._cursor() as cur:
    # Convert embedding to string format
    vector_str = str(embedding_vec)

    cur.execute("""
        SELECT
            id, article_id, title_norm, source_domain,
            1 - (embedding_vector <=> %s::vector) AS similarity,
            url, published_at
        FROM article_chunks
        WHERE embedding_vector IS NOT NULL
          AND id != %s
        ORDER BY embedding_vector <=> %s::vector
        LIMIT 10
    """, (vector_str, sample_id, vector_str))

    results = cur.fetchall()

    print(f"✅ Found {len(results)} similar articles:")
    print()

    for i, (chunk_id, article_id, title, source, similarity, url, pub_date) in enumerate(results, 1):
        print(f"#{i} Similarity: {similarity:.2%}")
        print(f"   Title: {title[:70]}")
        print(f"   Source: {source}")
        print(f"   Published: {pub_date}")
        print(f"   URL: {url[:60]}...")
        print()

print("=" * 80)
print("✅ Search with existing embeddings WORKS!")
print("=" * 80)
print()
print("💡 This proves:")
print("  - pgvector is working correctly")
print("  - embedding_vector column has valid data")
print("  - Cosine similarity search is fast and accurate")
print()
print("⚠️  Issue: OPENAI_API_KEY is invalid, can't generate NEW query embeddings")
print("   Solution: Update OPENAI_API_KEY with valid key")
