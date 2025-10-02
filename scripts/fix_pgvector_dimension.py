#!/usr/bin/env python3
"""Fix pgvector column to match actual embedding dimension (3072)"""

import os
import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from pg_client_new import PgClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def fix_dimension():
    client = PgClient()

    logger.info("Fixing pgvector dimension to 3072...")

    with client._cursor() as cur:
        # Drop old column if exists
        cur.execute("ALTER TABLE article_chunks DROP COLUMN IF EXISTS embedding_vector CASCADE")
        logger.info("✅ Dropped old embedding_vector column")

        # Create new column with correct dimension
        cur.execute("ALTER TABLE article_chunks ADD COLUMN embedding_vector vector(3072)")
        logger.info("✅ Added embedding_vector vector(3072) column")

        # Drop old function
        cur.execute("DROP FUNCTION IF EXISTS search_chunks_by_vector(vector, integer, float)")
        logger.info("✅ Dropped old search function")

        # Create new function with 3072 dimensions
        cur.execute("""
            CREATE OR REPLACE FUNCTION search_chunks_by_vector(
                query_vector vector(3072),
                result_limit INTEGER DEFAULT 10,
                similarity_threshold FLOAT DEFAULT 0.7
            )
            RETURNS TABLE (
                id BIGINT,
                article_id BIGINT,
                chunk_index INTEGER,
                text TEXT,
                url TEXT,
                title_norm TEXT,
                source_domain TEXT,
                similarity FLOAT
            ) AS $$
            BEGIN
                RETURN QUERY
                SELECT
                    ac.id,
                    ac.article_id,
                    ac.chunk_index,
                    ac.text,
                    ac.url,
                    ac.title_norm,
                    ac.source_domain,
                    1 - (ac.embedding_vector <=> query_vector) AS similarity
                FROM article_chunks ac
                WHERE ac.embedding_vector IS NOT NULL
                  AND (1 - (ac.embedding_vector <=> query_vector)) >= similarity_threshold
                ORDER BY ac.embedding_vector <=> query_vector
                LIMIT result_limit;
            END;
            $$ LANGUAGE plpgsql STABLE;
        """)
        logger.info("✅ Created search_chunks_by_vector function (3072 dim)")

    logger.info("✅ Dimension fix complete")
    logger.info("💡 Next: Run batch migration")
    logger.info("   python scripts/migrate_embeddings_batch.py --batch-size 50 --limit 1000")


if __name__ == '__main__':
    fix_dimension()
