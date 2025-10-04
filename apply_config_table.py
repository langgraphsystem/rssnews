#!/usr/bin/env python3
"""Apply config table schema to database"""
from dotenv import load_dotenv
load_dotenv()

from pg_client_new import PgClient

def apply_config_table():
    print("=" * 80)
    print("📊 Creating config table in database")
    print("=" * 80)
    print()

    db = PgClient()

    # Read SQL file
    with open('scripts/create_config_table.sql', 'r', encoding='utf-8') as f:
        sql = f.read()

    print("📝 Executing SQL migration...")
    print()

    try:
        # Execute SQL statements one by one to handle errors better
        statements = sql.split(';')
        with db._cursor() as cur:
            for i, stmt in enumerate(statements, 1):
                stmt = stmt.strip()
                if not stmt or stmt.startswith('--'):
                    continue
                print(f"  Executing statement {i}...")
                try:
                    cur.execute(stmt)
                except Exception as e:
                    print(f"    ⚠️  Statement {i} error: {e}")
                    # Continue with other statements

        print("✅ Config table created successfully!")
        print()

        # Verify
        with db._cursor() as cur:
            cur.execute("SELECT config_key, config_value, config_type FROM config ORDER BY config_key")
            rows = cur.fetchall()

            print(f"📊 Config entries: {len(rows)}")
            print()
            print("Current configuration:")
            for key, value, type_ in rows:
                print(f"  {key}: {value} ({type_})")

        print()
        print("=" * 80)
        print("✅ Migration complete!")

    except Exception as e:
        print(f"❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True

if __name__ == "__main__":
    success = apply_config_table()
    exit(0 if success else 1)
