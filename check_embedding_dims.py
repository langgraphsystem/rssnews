#!/usr/bin/env python3
"""Check embedding dimensions in database"""
import os
from dotenv import load_dotenv
load_dotenv()

from pg_client_new import PgClient

db = PgClient()

# Check latest embeddings
query = """
SELECT
    chunk_id,
    LENGTH(embedding::text) as text_len,
    vector_dims(embedding) as pgvector_dims,
    created_at
FROM article_chunks
WHERE embedding IS NOT NULL
ORDER BY created_at DESC
LIMIT 10;
"""

print("🔍 Последние 10 чанков с embeddings:\n")
print(f"{'Chunk ID':<12} {'TEXT len':<12} {'pgvector dims':<15} {'Created'}")
print("-" * 70)

with db._cursor() as cur:
    cur.execute(query)
    for row in cur.fetchall():
        chunk_id, text_len, dims, created_at = row
        print(f"{chunk_id:<12} {text_len:<12} {dims:<15} {created_at}")

# Check statistics
stats_query = """
SELECT
    COUNT(*) as total,
    COUNT(CASE WHEN vector_dims(embedding) = 3072 THEN 1 END) as dims_3072,
    COUNT(CASE WHEN vector_dims(embedding) != 3072 THEN 1 END) as dims_other
FROM article_chunks
WHERE embedding IS NOT NULL;
"""

print("\n📊 Статистика размерностей:\n")

with db._cursor() as cur:
    cur.execute(stats_query)
    total, dims_3072, dims_other = cur.fetchone()
    print(f"Всего embeddings: {total:,}")
    print(f"3072-dim (OpenAI): {dims_3072:,} ({dims_3072/total*100:.1f}%)")
    if dims_other > 0:
        print(f"⚠️  Другая размерность: {dims_other:,}")
