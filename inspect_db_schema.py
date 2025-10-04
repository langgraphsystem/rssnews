#!/usr/bin/env python3
"""Inspect production database schema"""
import os
from dotenv import load_dotenv
load_dotenv()

from database.production_db_client import ProductionDBClient

db = ProductionDBClient()

print("=" * 80)
print("🗄️  Database Schema Inspection")
print("=" * 80)
print()

# Check all tables and their columns
tables_to_inspect = ['raw', 'article_chunks', 'chunks', 'articles_index', 'feeds', 'config']

for table_name in tables_to_inspect:
    print(f"📋 Table: {table_name}")
    print("-" * 80)

    try:
        with db._cursor() as cur:
            # Check if table exists
            cur.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'public'
                    AND table_name = %s
                )
            """, (table_name,))

            exists = cur.fetchone()[0]

            if not exists:
                print(f"  ❌ Table does NOT exist")
                print()
                continue

            # Get columns
            cur.execute("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = %s
                ORDER BY ordinal_position
            """, (table_name,))

            columns = cur.fetchall()

            print(f"  ✅ Table exists with {len(columns)} columns:")
            for col_name, data_type, nullable in columns:
                nullable_str = "NULL" if nullable == "YES" else "NOT NULL"
                print(f"     - {col_name}: {data_type} {nullable_str}")

            # Row count
            cur.execute(f"SELECT COUNT(*) FROM {table_name}")
            row_count = cur.fetchone()[0]
            print(f"  📊 Rows: {row_count:,}")

            # Sample data
            if row_count > 0:
                cur.execute(f"SELECT * FROM {table_name} LIMIT 1")
                sample = cur.fetchone()
                col_names = [desc[0] for desc in cur.description]
                print(f"  🔍 Sample row:")
                for i, (col, val) in enumerate(zip(col_names, sample)):
                    val_str = str(val)[:50] + "..." if val and len(str(val)) > 50 else str(val)
                    print(f"     {col}: {val_str}")

    except Exception as e:
        print(f"  ❌ Error: {e}")

    print()
