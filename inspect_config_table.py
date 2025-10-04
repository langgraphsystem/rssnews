#!/usr/bin/env python3
"""Inspect config table schema"""
from dotenv import load_dotenv
load_dotenv()

from pg_client_new import PgClient

db = PgClient()

print("🔍 Inspecting config table schema:")
print()

with db._cursor() as cur:
    # Check if table exists
    cur.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name = 'config'
        )
    """)
    exists = cur.fetchone()[0]

    if not exists:
        print("❌ Config table does NOT exist")
    else:
        print("✅ Config table exists")
        print()

        # Get columns
        cur.execute("""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = 'config'
            ORDER BY ordinal_position
        """)

        print("Columns:")
        for col_name, data_type, nullable, default in cur.fetchall():
            nullable_str = "NULL" if nullable == "YES" else "NOT NULL"
            default_str = f" DEFAULT {default}" if default else ""
            print(f"  {col_name}: {data_type} {nullable_str}{default_str}")

        print()

        # Check sample data
        cur.execute("SELECT * FROM config LIMIT 5")
        rows = cur.fetchall()
        if rows:
            print(f"Sample data ({len(rows)} rows):")
            for row in rows:
                print(f"  {row}")
        else:
            print("No data in config table")
