#!/usr/bin/env python
"""
Migration Runner — Execute database migrations for Phase 3.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

try:
    import asyncpg
except ImportError:
    print("Error: asyncpg not installed. Install with: pip install asyncpg")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


async def run_migration(db_dsn: str, migration_file: Path):
    """
    Run a single migration file

    Args:
        db_dsn: PostgreSQL connection string
        migration_file: Path to SQL migration file
    """
    logger.info(f"Running migration: {migration_file.name}")

    # Read migration SQL
    sql = migration_file.read_text(encoding="utf-8")

    # Connect to database
    conn = await asyncpg.connect(dsn=db_dsn)

    try:
        # Execute migration in a transaction
        async with conn.transaction():
            await conn.execute(sql)

        logger.info(f"✅ Migration completed: {migration_file.name}")

    except Exception as e:
        logger.error(f"❌ Migration failed: {migration_file.name}")
        logger.error(f"Error: {e}")
        raise

    finally:
        await conn.close()


async def run_all_migrations(db_dsn: str, migrations_dir: Path):
    """
    Run all migrations in order

    Args:
        db_dsn: PostgreSQL connection string
        migrations_dir: Path to migrations directory
    """
    # Get all .sql files sorted by name
    migration_files = sorted(migrations_dir.glob("*.sql"))

    if not migration_files:
        logger.warning(f"No migration files found in {migrations_dir}")
        return

    logger.info(f"Found {len(migration_files)} migration(s)")

    for migration_file in migration_files:
        await run_migration(db_dsn, migration_file)

    logger.info("✅ All migrations completed successfully")


async def verify_pgvector(db_dsn: str):
    """
    Verify pgvector extension is installed

    Args:
        db_dsn: PostgreSQL connection string
    """
    conn = await asyncpg.connect(dsn=db_dsn)

    try:
        # Check if pgvector extension exists
        result = await conn.fetchrow(
            "SELECT * FROM pg_extension WHERE extname = 'vector'"
        )

        if result:
            logger.info("✅ pgvector extension is installed")
        else:
            logger.warning(
                "⚠️  pgvector extension not found. "
                "The migration will attempt to install it."
            )

    except Exception as e:
        logger.error(f"Failed to verify pgvector: {e}")

    finally:
        await conn.close()


async def verify_migration(db_dsn: str):
    """
    Verify migration was successful

    Args:
        db_dsn: PostgreSQL connection string
    """
    conn = await asyncpg.connect(dsn=db_dsn)

    try:
        # Check if memory_records table exists
        result = await conn.fetchrow(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'memory_records'
            """
        )

        if result:
            logger.info("✅ memory_records table exists")

            # Count records
            count = await conn.fetchval("SELECT COUNT(*) FROM memory_records")
            logger.info(f"   Records: {count}")

            # Check indexes
            indexes = await conn.fetch(
                """
                SELECT indexname
                FROM pg_indexes
                WHERE tablename = 'memory_records'
                """
            )
            logger.info(f"   Indexes: {len(indexes)}")
            for idx in indexes:
                logger.info(f"     - {idx['indexname']}")

        else:
            logger.error("❌ memory_records table not found")

    except Exception as e:
        logger.error(f"Verification failed: {e}")

    finally:
        await conn.close()


def main():
    """Main entry point"""
    # Get database DSN from environment
    db_dsn = os.getenv("PG_DSN")

    if not db_dsn:
        logger.error("PG_DSN environment variable not set")
        sys.exit(1)

    # Get migrations directory
    project_root = Path(__file__).parent.parent
    migrations_dir = project_root / "infra" / "migrations"

    if not migrations_dir.exists():
        logger.error(f"Migrations directory not found: {migrations_dir}")
        sys.exit(1)

    logger.info(f"Database: {db_dsn.split('@')[1] if '@' in db_dsn else 'localhost'}")
    logger.info(f"Migrations: {migrations_dir}")
    logger.info("=" * 60)

    # Run migrations
    try:
        # Verify pgvector
        asyncio.run(verify_pgvector(db_dsn))

        # Run all migrations
        asyncio.run(run_all_migrations(db_dsn, migrations_dir))

        # Verify migration
        logger.info("=" * 60)
        logger.info("Verifying migration...")
        asyncio.run(verify_migration(db_dsn))

        logger.info("=" * 60)
        logger.info("✅ Migration process completed successfully")

    except Exception as e:
        logger.error(f"❌ Migration process failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
