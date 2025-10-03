#!/usr/bin/env python3
import os
from dotenv import load_dotenv
load_dotenv()

from pg_client_new import PgClient

db = PgClient()

# Simple stats query
with db._cursor() as cur:
    cur.execute("""
        SELECT
            COUNT(*) as total,
            COUNT(CASE WHEN vector_dims(embedding) = 3072 THEN 1 END) as dims_3072,
            COUNT(CASE WHEN vector_dims(embedding) != 3072 THEN 1 END) as dims_other
        FROM article_chunks
        WHERE embedding IS NOT NULL;
    """)
    total, dims_3072, dims_other = cur.fetchone()

    print(f"✅ Всего embeddings: {total:,}")
    print(f"✅ 3072-dim (OpenAI text-embedding-3-large): {dims_3072:,} ({dims_3072/total*100:.1f}%)")
    if dims_other > 0:
        print(f"⚠️  Другая размерность: {dims_other:,}")
    else:
        print(f"✅ Все embeddings имеют правильную размерность 3072!")

# Sample one embedding to verify
with db._cursor() as cur:
    cur.execute("""
        SELECT vector_dims(embedding) as dims
        FROM article_chunks
        WHERE embedding IS NOT NULL
        ORDER BY created_at DESC
        LIMIT 1;
    """)
    result = cur.fetchone()
    if result:
        print(f"\n🔍 Последний добавленный embedding: {result[0]} размерностей")
