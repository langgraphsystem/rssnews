#!/usr/bin/env python3
"""Detect actual embedding dimension in database"""

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


def detect_dimension():
    client = PgClient()

    with client._cursor() as cur:
        cur.execute("""
            SELECT embedding
            FROM article_chunks
            WHERE embedding IS NOT NULL
            LIMIT 1
        """)

        row = cur.fetchone()
        if not row:
            logger.error("No embeddings found")
            return None

        embedding_json = row[0]

        if isinstance(embedding_json, str):
            embedding = json.loads(embedding_json)
        elif isinstance(embedding_json, list):
            embedding = embedding_json
        else:
            logger.error(f"Unknown format: {type(embedding_json)}")
            return None

        dim = len(embedding)
        logger.info(f"✅ Detected embedding dimension: {dim}")

        # Count total embeddings
        cur.execute("SELECT COUNT(*) FROM article_chunks WHERE embedding IS NOT NULL")
        total = cur.fetchone()[0]
        logger.info(f"📊 Total embeddings: {total:,}")

        return dim


if __name__ == '__main__':
    detect_dimension()
