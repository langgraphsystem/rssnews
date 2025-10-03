#!/usr/bin/env python3
"""Test database access from Railway"""
from dotenv import load_dotenv
load_dotenv()

from pg_client_new import PgClient

db = PgClient()
print('✅ Database connected')

with db._cursor() as cur:
    # Test 1: Count chunks with embeddings
    cur.execute('SELECT COUNT(*) FROM article_chunks WHERE embedding IS NOT NULL')
    count = cur.fetchone()[0]
    print(f'✅ Chunks with embeddings: {count:,}')

    # Test 2: Check embedding dimensions
    cur.execute('SELECT vector_dims(embedding) FROM article_chunks WHERE embedding IS NOT NULL LIMIT 1')
    dims = cur.fetchone()[0]
    print(f'✅ Embedding dimensions: {dims}')

    # Test 3: Count total articles
    cur.execute('SELECT COUNT(*) FROM raw')
    total = cur.fetchone()[0]
    print(f'✅ Total articles in raw: {total:,}')

    # Test 4: Sample search query
    cur.execute("""
        SELECT title_norm, source_domain, published_at
        FROM article_chunks
        WHERE embedding IS NOT NULL
        ORDER BY created_at DESC
        LIMIT 3
    """)
    print('\n📰 Recent articles with embeddings:')
    for title, source, published in cur.fetchall():
        print(f'  - {title[:60]}... ({source}) - {published}')

print('\n✅ All database tests passed!')
