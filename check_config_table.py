#!/usr/bin/env python3
"""Check system_config table structure"""
from database.production_db_client import ProductionDBClient

db = ProductionDBClient()

with db._cursor() as cur:
    # Check if table exists
    cur.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = 'system_config'
        )
    """)

    exists = cur.fetchone()[0]

    if exists:
        print("✅ Таблица system_config существует")

        # Get structure
        cur.execute("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'system_config'
            ORDER BY ordinal_position
        """)

        print("\n📋 Структура таблицы:")
        for col in cur.fetchall():
            print(f"   - {col[0]:<20} | {col[1]:<20} | NULL: {col[2]}")

        # Check data
        cur.execute("SELECT COUNT(*) FROM system_config")
        count = cur.fetchone()[0]
        print(f"\n📊 Записей: {count}")

        if count > 0:
            cur.execute("SELECT * FROM system_config LIMIT 5")
            print("\n🔍 Примеры:")
            for row in cur.fetchall():
                print(f"   {row}")

    else:
        print("❌ Таблица system_config не существует")
        print("\nНеобходимо создать таблицу с правильной структурой")
