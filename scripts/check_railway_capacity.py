#!/usr/bin/env python3
"""Check Railway PostgreSQL capacity for pgvector 3072-dim embeddings"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from pg_client_new import PgClient


def check_capacity():
    client = PgClient()

    print("=== Railway PostgreSQL Capacity Check ===\n")

    with client._cursor() as cur:
        # PostgreSQL version
        cur.execute('SELECT version()')
        version = cur.fetchone()[0]
        print(f"PostgreSQL: {version.split(',')[0]}\n")

        # pgvector extension
        cur.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
        pgvector = cur.fetchone()
        if pgvector:
            print(f"✅ pgvector: version {pgvector[0]}")
        else:
            print("❌ pgvector: NOT INSTALLED")
            return

        # Check vector column dimension
        cur.execute("""
            SELECT atttypmod
            FROM pg_attribute
            WHERE attrelid = 'article_chunks'::regclass
            AND attname = 'embedding_vector'
        """)
        result = cur.fetchone()
        if result and result[0] > 0:
            dimension = result[0] - 4
            print(f"✅ embedding_vector dimension: {dimension}")

            if dimension != 3072:
                print(f"⚠️  WARNING: Expected 3072, got {dimension}")
        else:
            print("❌ embedding_vector column not found or no dimension")

        print("\n=== Storage Analysis ===\n")

        # Current sizes
        cur.execute("""
            SELECT
                pg_size_pretty(pg_total_relation_size('article_chunks')) as total,
                pg_size_pretty(pg_relation_size('article_chunks')) as table,
                pg_size_pretty(pg_indexes_size('article_chunks')) as indexes
        """)
        total, table, indexes = cur.fetchone()
        print(f"Current total size: {total}")
        print(f"  Table data: {table}")
        print(f"  Indexes: {indexes}")

        # Migration estimates
        cur.execute('SELECT COUNT(*) FROM article_chunks WHERE embedding IS NOT NULL')
        total_embeddings = cur.fetchone()[0]

        cur.execute('SELECT COUNT(*) FROM article_chunks WHERE embedding_vector IS NOT NULL')
        migrated = cur.fetchone()[0]

        remaining = total_embeddings - migrated

        # Size calculations for vector(3072)
        # Each dimension = 4 bytes (float32)
        vector_size_bytes = 3072 * 4  # 12,288 bytes = 12 KB

        migrated_size_gb = (migrated * vector_size_bytes) / (1024**3)
        remaining_size_gb = (remaining * vector_size_bytes) / (1024**3)
        total_vectors_gb = (total_embeddings * vector_size_bytes) / (1024**3)

        print(f"\n=== Vector Storage Requirements ===\n")
        print(f"Embeddings: {total_embeddings:,} total")
        print(f"  Migrated: {migrated:,} ({migrated_size_gb:.2f} GB)")
        print(f"  Remaining: {remaining:,} ({remaining_size_gb:.2f} GB)")
        print(f"  Total vectors: {total_vectors_gb:.2f} GB")

        # HNSW index estimate (typically 20-40% of vector data)
        hnsw_index_gb = total_vectors_gb * 0.3
        total_with_index_gb = total_vectors_gb + hnsw_index_gb

        print(f"\nWith HNSW index:")
        print(f"  Index size (estimate): ~{hnsw_index_gb:.2f} GB")
        print(f"  Total with index: ~{total_with_index_gb:.2f} GB")

        # Railway limits check
        print(f"\n=== Railway PostgreSQL Plans ===\n")

        plans = {
            "Hobby (Free)": 0.5,
            "Pro": 8,
            "Team": 32,
            "Enterprise": 100
        }

        for plan_name, limit_gb in plans.items():
            if total_with_index_gb <= limit_gb:
                print(f"✅ {plan_name}: {limit_gb} GB - SUFFICIENT")
            else:
                needed = total_with_index_gb - limit_gb
                print(f"❌ {plan_name}: {limit_gb} GB - INSUFFICIENT (need +{needed:.1f} GB)")

        # Current database size
        cur.execute("""
            SELECT pg_size_pretty(pg_database_size(current_database()))
        """)
        db_size = cur.fetchone()[0]
        print(f"\n=== Current Database ===")
        print(f"Total size: {db_size}")

        # Recommendations
        print(f"\n=== Recommendations ===\n")

        if total_with_index_gb < 0.5:
            print("✅ Hobby (Free) plan is sufficient")
        elif total_with_index_gb < 8:
            print("⚠️  Upgrade to Pro plan recommended")
            print(f"   (need {total_with_index_gb:.1f} GB, Pro has 8 GB)")
        elif total_with_index_gb < 32:
            print("⚠️  Upgrade to Team plan required")
            print(f"   (need {total_with_index_gb:.1f} GB, Team has 32 GB)")
        else:
            print("⚠️  Enterprise plan required")
            print(f"   (need {total_with_index_gb:.1f} GB)")

        # Alternative: Don't migrate old embeddings
        print(f"\n💡 Alternative Strategy:")
        print(f"   Keep last 30 days only in pgvector")

        cur.execute("""
            SELECT COUNT(*)
            FROM article_chunks
            WHERE embedding IS NOT NULL
            AND published_at > NOW() - INTERVAL '30 days'
        """)
        recent_count = cur.fetchone()[0]
        recent_size_gb = (recent_count * vector_size_bytes) / (1024**3)
        recent_with_index_gb = recent_size_gb * 1.3

        print(f"   Recent (30d): {recent_count:,} embeddings")
        print(f"   Space needed: ~{recent_with_index_gb:.2f} GB")
        print(f"   Savings: {total_with_index_gb - recent_with_index_gb:.1f} GB")


if __name__ == '__main__':
    try:
        check_capacity()
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
