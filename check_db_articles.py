#!/usr/bin/env python3
"""Check article_chunks data and timestamps"""

import os
import psycopg2
from datetime import datetime

dsn = os.getenv('PG_DSN')
if not dsn:
    print("ERROR: PG_DSN not set")
    exit(1)

conn = psycopg2.connect(dsn)
cur = conn.cursor()

# Check total chunks with embeddings
cur.execute('SELECT COUNT(*) FROM article_chunks WHERE embedding_vector IS NOT NULL')
total_with_embeddings = cur.fetchone()[0]
print(f'Total chunks with embeddings: {total_with_embeddings:,}')

# Check recent chunks (last 24h)
cur.execute("""
    SELECT COUNT(*)
    FROM article_chunks
    WHERE embedding_vector IS NOT NULL
      AND published_at >= NOW() - INTERVAL '24 hours'
""")
recent_24h = cur.fetchone()[0]
print(f'Chunks with embeddings in last 24h: {recent_24h:,}')

# Check recent chunks (last 7 days)
cur.execute("""
    SELECT COUNT(*)
    FROM article_chunks
    WHERE embedding_vector IS NOT NULL
      AND published_at >= NOW() - INTERVAL '7 days'
""")
recent_7d = cur.fetchone()[0]
print(f'Chunks with embeddings in last 7 days: {recent_7d:,}')

# Get most recent published_at
cur.execute("""
    SELECT MAX(published_at)
    FROM article_chunks
    WHERE embedding_vector IS NOT NULL
""")
most_recent = cur.fetchone()[0]
print(f'Most recent article timestamp: {most_recent}')

# Get some sample published_at values
cur.execute("""
    SELECT published_at, title_norm, source_domain
    FROM article_chunks
    WHERE embedding_vector IS NOT NULL
    ORDER BY published_at DESC NULLS LAST
    LIMIT 5
""")
print('\nMost recent articles:')
for row in cur.fetchall():
    ts = row[0].strftime('%Y-%m-%d %H:%M:%S') if row[0] else 'NULL'
    title = row[1][:60] if row[1] else 'No title'
    print(f'  {ts} | {row[2]} | {title}...')

conn.close()
