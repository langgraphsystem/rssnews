#!/usr/bin/env python3
"""
Database analysis script for RSS News System
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor
import json
from datetime import datetime

def get_database_info():
    """Get comprehensive database structure and sample data"""

    # Use connection string from .env
    dsn = "postgres://postgres:ug1Hi~XHEMdMh_Lm~4UfUKtAejqLBGdg@crossover.proxy.rlwy.net:12306/railway"

    try:
        conn = psycopg2.connect(dsn)
        conn.autocommit = True

        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            print("🔗 Connected to database successfully!")
            print("=" * 80)

            # Get all tables
            cur.execute("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                ORDER BY table_name
            """)
            tables = [row['table_name'] for row in cur.fetchall()]

            print(f"📊 Found {len(tables)} tables:")
            for table in tables:
                print(f"  • {table}")
            print()

            # Analyze each table
            for table_name in tables:
                print(f"📋 TABLE: {table_name}")
                print("-" * 60)

                # Get table structure
                cur.execute("""
                    SELECT
                        column_name,
                        data_type,
                        is_nullable,
                        column_default,
                        character_maximum_length
                    FROM information_schema.columns
                    WHERE table_name = %s
                    ORDER BY ordinal_position
                """, (table_name,))

                columns = cur.fetchall()
                print(f"Columns ({len(columns)}):")
                for col in columns:
                    nullable = "NULL" if col['is_nullable'] == 'YES' else "NOT NULL"
                    default = f", default: {col['column_default']}" if col['column_default'] else ""
                    max_len = f"({col['character_maximum_length']})" if col['character_maximum_length'] else ""
                    print(f"  • {col['column_name']}: {col['data_type']}{max_len} {nullable}{default}")

                # Get row count
                try:
                    cur.execute(f"SELECT COUNT(*) as count FROM {table_name}")
                    count = cur.fetchone()['count']
                    print(f"\nRow count: {count:,}")
                except Exception as e:
                    print(f"\nRow count: Error - {e}")

                # Get sample data (first 3 rows)
                if count > 0:
                    try:
                        cur.execute(f"SELECT * FROM {table_name} LIMIT 3")
                        samples = cur.fetchall()
                        print(f"\nSample data (first {len(samples)} rows):")
                        for i, row in enumerate(samples, 1):
                            print(f"  Row {i}:")
                            for key, value in row.items():
                                # Truncate long values
                                if isinstance(value, str) and len(value) > 100:
                                    value = value[:100] + "..."
                                print(f"    {key}: {value}")
                    except Exception as e:
                        print(f"\nSample data: Error - {e}")

                # Get indexes
                try:
                    cur.execute("""
                        SELECT indexname, indexdef
                        FROM pg_indexes
                        WHERE tablename = %s
                        ORDER BY indexname
                    """, (table_name,))
                    indexes = cur.fetchall()
                    if indexes:
                        print(f"\nIndexes ({len(indexes)}):")
                        for idx in indexes:
                            print(f"  • {idx['indexname']}")
                            print(f"    {idx['indexdef']}")
                except Exception as e:
                    print(f"\nIndexes: Error - {e}")

                print("\n" + "=" * 80 + "\n")

        conn.close()

    except Exception as e:
        print(f"❌ Database connection error: {e}")

if __name__ == "__main__":
    get_database_info()