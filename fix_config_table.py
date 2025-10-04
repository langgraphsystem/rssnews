#!/usr/bin/env python3
"""Fix config table schema - drop old and create new"""
import os
from dotenv import load_dotenv
load_dotenv()

import psycopg2

PG_DSN = os.getenv("PG_DSN")
if not PG_DSN:
    print("❌ PG_DSN not set")
    exit(1)

print("=" * 80)
print("🔧 Fixing config table schema")
print("=" * 80)
print()

conn = psycopg2.connect(PG_DSN)
conn.autocommit = True
cur = conn.cursor()

try:
    # Drop old table
    print("📝 Dropping old config table...")
    cur.execute("DROP TABLE IF EXISTS config CASCADE")
    print("✅ Old table dropped")
    print()

    # Create new table with correct schema
    print("📝 Creating new config table...")
    cur.execute("""
        CREATE TABLE config (
            config_key TEXT PRIMARY KEY,
            config_value TEXT NOT NULL,
            config_type TEXT NOT NULL DEFAULT 'string',
            description TEXT,
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            updated_by TEXT DEFAULT 'system'
        )
    """)
    print("✅ Table created")
    print()

    # Create index
    print("📝 Creating index...")
    cur.execute("CREATE INDEX idx_config_key ON config(config_key)")
    print("✅ Index created")
    print()

    # Insert default values
    print("📝 Inserting default scoring weights...")
    cur.execute("""
        INSERT INTO config (config_key, config_value, config_type, description) VALUES
            ('scoring.semantic_weight', '0.58', 'float', 'Weight for semantic similarity score'),
            ('scoring.fts_weight', '0.32', 'float', 'Weight for full-text search score'),
            ('scoring.freshness_weight', '0.06', 'float', 'Weight for article freshness'),
            ('scoring.source_weight', '0.04', 'float', 'Weight for source reputation'),
            ('scoring.tau_hours', '72', 'int', 'Time decay parameter in hours'),
            ('scoring.max_per_domain', '3', 'int', 'Maximum results per domain'),
            ('scoring.max_per_article', '2', 'int', 'Maximum chunks per article')
    """)
    print("✅ Default values inserted")
    print()

    # Verify
    cur.execute("SELECT config_key, config_value, config_type FROM config ORDER BY config_key")
    rows = cur.fetchall()

    print(f"📊 Config entries: {len(rows)}")
    print()
    print("Current configuration:")
    for key, value, type_ in rows:
        print(f"  {key}: {value} ({type_})")

    print()
    print("=" * 80)
    print("✅ Config table fixed successfully!")
    print("=" * 80)

except Exception as e:
    print(f"❌ Error: {e}")
    conn.rollback()
    import traceback
    traceback.print_exc()
    exit(1)
finally:
    cur.close()
    conn.close()
