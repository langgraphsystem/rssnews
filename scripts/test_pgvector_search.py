#!/usr/bin/env python3
"""Test pgvector search directly using pre-computed embedding"""

import os
import sys
import json
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from pg_client_new import PgClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_pgvector():
    client = PgClient()

    # Get a sample embedding from database
    with client._cursor() as cur:
        cur.execute("""
            SELECT embedding_vector
            FROM article_chunks
            WHERE embedding_vector IS NOT NULL
            LIMIT 1
        """)

        row = cur.fetchone()
        if not row:
            logger.error("No pgvector embeddings found")
            return

        test_vector = row[0]

    logger.info(f"Using test vector: {str(test_vector)[:100]}...")

    # Test pgvector search
    with client._cursor() as cur:
        cur.execute("""
            SELECT
                id, title_norm, source_domain,
                1 - (embedding_vector <=> %s::vector) AS similarity
            FROM article_chunks
            WHERE embedding_vector IS NOT NULL
            ORDER BY embedding_vector <=> %s::vector
            LIMIT 5
        """, (test_vector, test_vector))

        results = cur.fetchall()

        logger.info(f"✅ pgvector search successful: {len(results)} results")

        for i, row in enumerate(results, 1):
            id, title, source, sim = row
            logger.info(f"  {i}. [{sim:.3f}] {title[:60]} - {source}")


if __name__ == '__main__':
    test_pgvector()
