#!/usr/bin/env python3
"""
Apply pgvector migration to enable native vector search

Usage:
    python scripts/apply_pgvector_migration.py

Requirements:
    - PostgreSQL with pgvector extension installed
    - PG_DSN environment variable set
"""

import os
import sys
import logging
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from pg_client_new import PgClient

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def apply_pgvector_migration():
    """Apply pgvector migration to database"""

    if not os.getenv('PG_DSN'):
        logger.error("PG_DSN environment variable not set")
        return False

    try:
        client = PgClient()
        logger.info("Connected to database")

        # Read migration SQL
        migration_path = Path(__file__).parent.parent / 'infra' / 'migrations' / '004_enable_pgvector.sql'

        if not migration_path.exists():
            logger.error(f"Migration file not found: {migration_path}")
            return False

        with open(migration_path, 'r', encoding='utf-8') as f:
            migration_sql = f.read()

        logger.info("Applying pgvector migration...")

        # Execute migration
        with client._cursor() as cur:
            cur.execute(migration_sql)

        logger.info("✅ Migration applied successfully")

        # Verify pgvector is enabled
        with client._cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM pg_extension WHERE extname = 'vector'")
            count = cur.fetchone()[0]

            if count > 0:
                logger.info("✅ pgvector extension is installed")
            else:
                logger.warning("⚠️ pgvector extension not found - vector search will use Python fallback")

        # Check if embedding_vector column exists
        with client._cursor() as cur:
            cur.execute("""
                SELECT COUNT(*)
                FROM information_schema.columns
                WHERE table_name = 'article_chunks'
                  AND column_name = 'embedding_vector'
            """)
            count = cur.fetchone()[0]

            if count > 0:
                logger.info("✅ embedding_vector column added")
            else:
                logger.error("❌ embedding_vector column not found")
                return False

        # Count migrated embeddings
        with client._cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM article_chunks WHERE embedding_vector IS NOT NULL")
            migrated = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM article_chunks WHERE embedding IS NOT NULL")
            total = cur.fetchone()[0]

            logger.info(f"📊 Migrated embeddings: {migrated}/{total}")

            if migrated < total:
                logger.warning(f"⚠️ {total - migrated} embeddings still need migration")
                logger.info("Run this script again to complete migration")

        return True

    except Exception as e:
        logger.error(f"Migration failed: {e}", exc_info=True)
        return False


if __name__ == '__main__':
    success = apply_pgvector_migration()
    sys.exit(0 if success else 1)
