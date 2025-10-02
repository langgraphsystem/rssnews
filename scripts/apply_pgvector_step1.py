#!/usr/bin/env python3
"""Apply pgvector migration step 1: schema changes only"""

import os
import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from pg_client_new import PgClient

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def apply_step1():
    if not os.getenv('PG_DSN'):
        logger.error("PG_DSN environment variable not set")
        return False

    try:
        client = PgClient()
        logger.info("Connected to database")

        migration_path = Path(__file__).parent.parent / 'infra' / 'migrations' / '004_enable_pgvector_step1.sql'

        with open(migration_path, 'r', encoding='utf-8') as f:
            sql = f.read()

        logger.info("Applying step 1: schema changes...")

        with client._cursor() as cur:
            cur.execute(sql)

        logger.info("✅ Step 1 complete: pgvector extension enabled, column added")
        logger.info("💡 Next: Run batch migration script")
        logger.info("   python scripts/migrate_embeddings_batch.py --batch-size 100 --limit 1000")

        return True

    except Exception as e:
        logger.error(f"Migration failed: {e}", exc_info=True)
        return False


if __name__ == '__main__':
    success = apply_step1()
    sys.exit(0 if success else 1)
