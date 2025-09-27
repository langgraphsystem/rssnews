#!/usr/bin/env python3
"""
Additional database analysis for remaining tables
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor
import json

def analyze_remaining_tables():
    """Analyze search_logs, system_config, user_interactions"""

    dsn = "postgres://postgres:ug1Hi~XHEMdMh_Lm~4UfUKtAejqLBGdg@crossover.proxy.rlwy.net:12306/railway"

    try:
        conn = psycopg2.connect(dsn)
        conn.autocommit = True

        remaining_tables = ['search_logs', 'system_config', 'user_interactions']

        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            for table_name in remaining_tables:
                print(f"📋 TABLE: {table_name}")
                print("-" * 60)

                # Get table structure
                cur.execute("""
                    SELECT
                        column_name,
                        data_type,
                        is_nullable,
                        column_default,
                        character_maximum_length
                    FROM information_schema.columns
                    WHERE table_name = %s
                    ORDER BY ordinal_position
                """, (table_name,))

                columns = cur.fetchall()
                print(f"Columns ({len(columns)}):")
                for col in columns:
                    nullable = "NULL" if col['is_nullable'] == 'YES' else "NOT NULL"
                    default = f", default: {col['column_default']}" if col['column_default'] else ""
                    max_len = f"({col['character_maximum_length']})" if col['character_maximum_length'] else ""
                    print(f"  • {col['column_name']}: {col['data_type']}{max_len} {nullable}{default}")

                # Get row count
                try:
                    cur.execute(f"SELECT COUNT(*) as count FROM {table_name}")
                    count = cur.fetchone()['count']
                    print(f"\nRow count: {count:,}")
                except Exception as e:
                    print(f"\nRow count: Error - {e}")

                # Get sample data if exists
                if count > 0:
                    try:
                        cur.execute(f"SELECT * FROM {table_name} LIMIT 3")
                        samples = cur.fetchall()
                        print(f"\nSample data (first {len(samples)} rows):")
                        for i, row in enumerate(samples, 1):
                            print(f"  Row {i}:")
                            for key, value in row.items():
                                # Truncate long values
                                if isinstance(value, str) and len(value) > 100:
                                    value = value[:100] + "..."
                                print(f"    {key}: {value}")
                    except Exception as e:
                        print(f"\nSample data: Error - {e}")

                # Get indexes
                try:
                    cur.execute("""
                        SELECT indexname, indexdef
                        FROM pg_indexes
                        WHERE tablename = %s
                        ORDER BY indexname
                    """, (table_name,))
                    indexes = cur.fetchall()
                    if indexes:
                        print(f"\nIndexes ({len(indexes)}):")
                        for idx in indexes:
                            print(f"  • {idx['indexname']}")
                            print(f"    {idx['indexdef']}")
                    else:
                        print(f"\nIndexes: None")
                except Exception as e:
                    print(f"\nIndexes: Error - {e}")

                print("\n" + "=" * 80 + "\n")

            # Additional analysis: Get vector embedding info
            print("🧠 VECTOR EMBEDDINGS ANALYSIS")
            print("-" * 60)

            # Check embedding dimensions and types
            cur.execute("""
                SELECT
                    COUNT(*) as total_chunks,
                    COUNT(embedding) as has_embedding,
                    COUNT(embedding_1536) as has_embedding_1536,
                    COUNT(fts_vector) as has_fts_vector
                FROM article_chunks
            """)

            vector_stats = cur.fetchone()
            print(f"Total chunks: {vector_stats['total_chunks']:,}")
            print(f"Has embedding (768D): {vector_stats['has_embedding']:,}")
            print(f"Has embedding_1536 (1536D): {vector_stats['has_embedding_1536']:,}")
            print(f"Has FTS vectors: {vector_stats['has_fts_vector']:,}")

            # Check embedding sample
            cur.execute("""
                SELECT
                    array_length(embedding, 1) as embedding_dim,
                    array_length(embedding_1536, 1) as embedding_1536_dim
                FROM article_chunks
                WHERE embedding IS NOT NULL
                LIMIT 1
            """)

            result = cur.fetchone()
            if result:
                print(f"Sample embedding dimensions: {result['embedding_dim']} / {result['embedding_1536_dim']}")

        conn.close()

    except Exception as e:
        print(f"❌ Database connection error: {e}")

if __name__ == "__main__":
    analyze_remaining_tables()