"""
Apply Phase 4 database migration to Railway PostgreSQL
"""

import os
import sys
import asyncio
import asyncpg
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


async def apply_migration():
    """Apply Phase 4 migration to database"""

    # Get PG_DSN from environment
    pg_dsn = os.getenv('PG_DSN')

    if not pg_dsn:
        print("❌ PG_DSN environment variable not set")
        print("Please set PG_DSN in .env file or environment")
        return False

    print(f"📊 Connecting to PostgreSQL...")

    try:
        # Connect to database
        conn = await asyncpg.connect(pg_dsn)
        print("✅ Connected to database")

        # Read migration file
        migration_file = Path(__file__).parent.parent / "infra" / "migrations" / "003_create_phase4_tables.sql"

        if not migration_file.exists():
            print(f"❌ Migration file not found: {migration_file}")
            await conn.close()
            return False

        print(f"📄 Reading migration: {migration_file.name}")
        migration_sql = migration_file.read_text(encoding='utf-8')

        # Execute migration
        print("🔄 Applying migration...")
        await conn.execute(migration_sql)
        print("✅ Migration applied successfully")

        # Verify tables created
        tables = await conn.fetch("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name LIKE 'phase4%'
            ORDER BY table_name
        """)

        print(f"\n📦 Created {len(tables)} Phase 4 tables:")
        for row in tables:
            print(f"   ✅ {row['table_name']}")

        # Close connection
        await conn.close()
        print("\n🎉 Phase 4 database migration complete!")
        return True

    except Exception as e:
        print(f"❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    # Load .env file if it exists
    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        print(f"📋 Loading environment from {env_file}")
        with open(env_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key] = value

    # Run migration
    success = asyncio.run(apply_migration())
    sys.exit(0 if success else 1)
