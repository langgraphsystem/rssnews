#!/usr/bin/env python3
"""Test the exact search query being used"""

import os
import sys
import psycopg2
import asyncio
sys.path.insert(0, os.path.dirname(__file__))

from openai_embedding_generator import OpenAIEmbeddingGenerator

async def main():
    dsn = os.getenv('PG_DSN')
    if not dsn:
        print("ERROR: PG_DSN not set")
        exit(1)

    # Generate embedding for "trump"
    gen = OpenAIEmbeddingGenerator()
    embeddings = await gen.generate_embeddings(["trump"])
    if not embeddings or not embeddings[0]:
        print("ERROR: Failed to generate embedding")
        exit(1)

    query_embedding = embeddings[0]
    print(f"Generated {len(query_embedding)}-dim embedding for 'trump'")

    # Connect to database
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()

    # Test the exact query from search_with_time_filter
    vector_str = '[' + ','.join(str(x) for x in query_embedding) + ']'
    hours = 24

    query_sql = """
        SELECT
            ac.id, ac.article_id, ac.chunk_index, ac.text,
            ac.url, ac.title_norm, ac.source_domain, ac.published_at,
            1 - (ac.embedding_vector <=> %s::vector) AS similarity
        FROM article_chunks ac
        WHERE ac.embedding_vector IS NOT NULL
          AND ac.published_at >= NOW() - (%s || ' hours')::interval
        ORDER BY ac.embedding_vector <=> %s::vector
        LIMIT %s
    """

    params = [vector_str, hours, vector_str, 10]

    print(f"\nExecuting query with params: hours={hours}, limit=10")
    print(f"Vector dimension check: {len(query_embedding)}")

    try:
        cur.execute(query_sql, params)
        results = cur.fetchall()
        print(f"\n✅ Query successful! Found {len(results)} results")

        if results:
            print("\nTop 3 results:")
            for i, row in enumerate(results[:3], 1):
                print(f"{i}. {row[5][:60]}... (similarity: {row[8]:.3f})")
        else:
            print("\n⚠️ Query returned 0 results")

            # Debug: check if there are ANY articles with embeddings
            cur.execute("SELECT COUNT(*) FROM article_chunks WHERE embedding_vector IS NOT NULL")
            total = cur.fetchone()[0]
            print(f"   Total chunks with embeddings: {total:,}")

    except Exception as e:
        print(f"\n❌ Query failed: {e}")
        import traceback
        traceback.print_exc()

    conn.close()

if __name__ == "__main__":
    asyncio.run(main())
