#!/usr/bin/env python3
"""Check existing tables in database"""
from dotenv import load_dotenv
load_dotenv()

from pg_client_new import PgClient

db = PgClient()

with db._cursor() as cur:
    cur.execute("""
        SELECT tablename
        FROM pg_tables
        WHERE schemaname = 'public'
        ORDER BY tablename
    """)
    tables = [row[0] for row in cur.fetchall()]

print("📊 Existing tables:")
for table in tables:
    print(f"  - {table}")

# Check if config table exists
if 'config' in tables:
    print("\n✅ Config table exists")
    with db._cursor() as cur:
        cur.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'config'
            ORDER BY ordinal_position
        """)
        print("\nConfig table schema:")
        for col_name, col_type in cur.fetchall():
            print(f"  {col_name}: {col_type}")
else:
    print("\n❌ Config table does NOT exist")
