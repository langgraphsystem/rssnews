#!/usr/bin/env python3
"""
Apply migration 006 - Add source_query column to user_interactions
"""
import os
import sys
import psycopg2

def apply_migration():
    """Apply migration to add source_query column"""
    pg_dsn = os.getenv("PG_DSN") or os.getenv("DATABASE_URL")

    if not pg_dsn:
        print("❌ Error: PG_DSN or DATABASE_URL environment variable not set")
        sys.exit(1)

    try:
        print("🔌 Connecting to database...")
        conn = psycopg2.connect(pg_dsn)
        cur = conn.cursor()

        print("📝 Reading migration file...")
        with open("infra/migrations/006_add_source_query_to_interactions.sql", "r") as f:
            migration_sql = f.read()

        print("🚀 Applying migration 006...")
        cur.execute(migration_sql)
        conn.commit()

        print("✅ Migration 006 applied successfully!")

        # Verify column exists
        cur.execute("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'user_interactions'
            AND column_name = 'source_query'
        """)

        result = cur.fetchone()
        if result:
            print(f"✅ Verified: source_query column exists ({result[1]})")
        else:
            print("⚠️  Warning: Could not verify column existence")

        cur.close()
        conn.close()

    except Exception as e:
        print(f"❌ Migration failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    apply_migration()
