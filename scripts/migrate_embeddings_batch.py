#!/usr/bin/env python3
"""
Batch migrate embeddings from JSON to pgvector format

This script migrates embeddings in small batches to avoid memory issues.
Designed to work with Railway PostgreSQL memory constraints.

Usage:
    python scripts/migrate_embeddings_batch.py [--batch-size 100] [--limit 1000]
"""

import os
import sys
import json
import logging
import argparse
from pathlib import Path
from typing import List, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from pg_client_new import PgClient

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def migrate_batch(client: PgClient, chunk_ids: List[int]) -> Tuple[int, int]:
    """Migrate a batch of embeddings from JSON to vector format"""

    success_count = 0
    error_count = 0

    try:
        with client._cursor() as cur:
            # Fetch embeddings for this batch
            cur.execute("""
                SELECT id, embedding
                FROM article_chunks
                WHERE id = ANY(%s)
                  AND embedding IS NOT NULL
                  AND embedding_vector IS NULL
            """, (chunk_ids,))

            rows = cur.fetchall()

            for row_id, embedding_json in rows:
                try:
                    # Parse JSON embedding
                    if isinstance(embedding_json, str):
                        embedding_list = json.loads(embedding_json)
                    elif isinstance(embedding_json, list):
                        embedding_list = embedding_json
                    else:
                        logger.warning(f"Chunk {row_id}: Unknown embedding format, skipping")
                        error_count += 1
                        continue

                    # Auto-detect dimension (support 768, 1536, 3072)
                    dim = len(embedding_list)
                    if dim not in (768, 1536, 3072):
                        logger.warning(f"Chunk {row_id}: Unsupported dimension {dim}")
                        error_count += 1
                        continue

                    # Convert to pgvector format string
                    vector_str = '[' + ','.join(str(float(x)) for x in embedding_list) + ']'

                    # Update with vector
                    cur.execute("""
                        UPDATE article_chunks
                        SET embedding_vector = %s::vector
                        WHERE id = %s
                    """, (vector_str, row_id))

                    success_count += 1

                except Exception as e:
                    logger.error(f"Chunk {row_id}: Migration failed - {e}")
                    error_count += 1
                    continue

    except Exception as e:
        logger.error(f"Batch migration failed: {e}")
        return success_count, error_count

    return success_count, error_count


def migrate_embeddings(batch_size: int = 100, limit: int = None):
    """Migrate embeddings in batches"""

    if not os.getenv('PG_DSN'):
        logger.error("PG_DSN environment variable not set")
        return False

    try:
        client = PgClient()
        logger.info("Connected to database")

        # Check if embedding_vector column exists
        with client._cursor() as cur:
            cur.execute("""
                SELECT COUNT(*)
                FROM information_schema.columns
                WHERE table_name = 'article_chunks'
                  AND column_name = 'embedding_vector'
            """)

            if cur.fetchone()[0] == 0:
                logger.error("embedding_vector column not found. Run step1 migration first:")
                logger.error("  psql $PG_DSN -f infra/migrations/004_enable_pgvector_step1.sql")
                return False

        # Count total embeddings to migrate
        with client._cursor() as cur:
            cur.execute("""
                SELECT COUNT(*)
                FROM article_chunks
                WHERE embedding IS NOT NULL
                  AND embedding_vector IS NULL
            """)
            total_pending = cur.fetchone()[0]

            cur.execute("""
                SELECT COUNT(*)
                FROM article_chunks
                WHERE embedding_vector IS NOT NULL
            """)
            already_migrated = cur.fetchone()[0]

        logger.info(f"📊 Migration status:")
        logger.info(f"   Already migrated: {already_migrated}")
        logger.info(f"   Pending: {total_pending}")

        if total_pending == 0:
            logger.info("✅ All embeddings already migrated!")
            return True

        # Apply limit if specified
        if limit and limit < total_pending:
            logger.info(f"⚠️ Limiting migration to {limit} embeddings (--limit {limit})")
            total_to_migrate = limit
        else:
            total_to_migrate = total_pending

        # Fetch IDs to migrate
        with client._cursor() as cur:
            cur.execute("""
                SELECT id
                FROM article_chunks
                WHERE embedding IS NOT NULL
                  AND embedding_vector IS NULL
                ORDER BY id
                LIMIT %s
            """, (total_to_migrate,))

            all_ids = [row[0] for row in cur.fetchall()]

        logger.info(f"🚀 Starting migration of {len(all_ids)} embeddings (batch_size={batch_size})")

        # Process in batches
        total_success = 0
        total_errors = 0

        for i in range(0, len(all_ids), batch_size):
            batch_ids = all_ids[i:i + batch_size]
            batch_num = (i // batch_size) + 1
            total_batches = (len(all_ids) + batch_size - 1) // batch_size

            logger.info(f"Processing batch {batch_num}/{total_batches} ({len(batch_ids)} chunks)...")

            success, errors = migrate_batch(client, batch_ids)
            total_success += success
            total_errors += errors

            if (batch_num % 10) == 0:
                logger.info(f"Progress: {total_success}/{len(all_ids)} ({100*total_success//len(all_ids)}%)")

        logger.info(f"✅ Migration complete!")
        logger.info(f"   Migrated: {total_success}")
        logger.info(f"   Errors: {total_errors}")
        logger.info(f"   Total: {already_migrated + total_success}")

        if total_errors > 0:
            logger.warning(f"⚠️ {total_errors} embeddings failed to migrate")

        # Final status
        with client._cursor() as cur:
            cur.execute("""
                SELECT COUNT(*)
                FROM article_chunks
                WHERE embedding_vector IS NOT NULL
            """)
            final_count = cur.fetchone()[0]

        logger.info(f"📊 Final count: {final_count} embeddings in pgvector format")

        if total_pending > total_to_migrate:
            remaining = total_pending - total_to_migrate
            logger.info(f"💡 Run again to migrate remaining {remaining} embeddings")
        else:
            logger.info("💡 Next step: Create HNSW index")
            logger.info("   psql $PG_DSN -f infra/migrations/004_enable_pgvector_step2.sql")

        return True

    except Exception as e:
        logger.error(f"Migration failed: {e}", exc_info=True)
        return False


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Batch migrate embeddings to pgvector')
    parser.add_argument('--batch-size', type=int, default=100,
                       help='Number of embeddings per batch (default: 100)')
    parser.add_argument('--limit', type=int, default=None,
                       help='Max embeddings to migrate (default: all)')

    args = parser.parse_args()

    success = migrate_embeddings(batch_size=args.batch_size, limit=args.limit)
    sys.exit(0 if success else 1)
