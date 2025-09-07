#!/usr/bin/env python3
"""
Исправление схемы PostgreSQL для корректной работы миграции
Этот скрипт пересоздает таблицы с правильной структурой
"""
import os
import sys

if 'PG_DSN' not in os.environ:
    print("❌ Переменная окружения PG_DSN не установлена.")
    print("   Установите ее перед запуском: set PG_DSN=...")
    sys.exit(1)
print("✅ PG_DSN найдена.")

def fix_schema():
    """Исправляет схему БД"""
    try:
        import psycopg2
        
        dsn = os.environ['PG_DSN']
        conn = psycopg2.connect(dsn)
        conn.autocommit = True
        
        with conn.cursor() as cur:
            print("🔧 Удаляем старые таблицы (если есть)...")
            
            # Удаляем таблицы в правильном порядке (из-за зависимостей)
            tables_to_drop = ['articles_index', 'raw', 'feeds', 'diagnostics', 'config']
            
            for table in tables_to_drop:
                try:
                    cur.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
                    print(f"✅ Таблица {table} удалена")
                except Exception as e:
                    print(f"⚠️ Не удалось удалить таблицу {table}: {e}")
            
            print("\n🏗️ Создаем новую схему...")
            
            # Создаем таблицы заново
            schema_sql = """
            -- feeds
            CREATE TABLE IF NOT EXISTS feeds (
              id SERIAL PRIMARY KEY,
              feed_url TEXT,
              feed_url_canon TEXT UNIQUE NOT NULL,
              lang TEXT,
              status TEXT DEFAULT 'active',
              last_entry_date TEXT,
              last_crawled TEXT,
              no_updates_days INTEGER,
              etag TEXT,
              last_modified TEXT,
              health_score TEXT,
              notes TEXT,
              checked_at TEXT,
              updated_at TIMESTAMPTZ DEFAULT NOW()
            );

            -- raw
            CREATE TABLE IF NOT EXISTS raw (
              id BIGSERIAL PRIMARY KEY,
              row_id INTEGER,
              source TEXT,
              feed_url TEXT,
              article_url TEXT,
              article_url_canon TEXT,
              url_hash TEXT UNIQUE NOT NULL,
              text_hash TEXT,
              found_at TEXT,
              fetched_at TEXT,
              published_at TEXT,
              language TEXT,
              title TEXT,
              subtitle TEXT,
              authors TEXT,
              section TEXT,
              tags TEXT,
              article_type TEXT,
              clean_text TEXT,
              clean_text_len INTEGER,
              full_text_ref TEXT,
              full_text_len INTEGER,
              word_count INTEGER,
              out_links TEXT,
              category_guess TEXT,
              status TEXT DEFAULT 'pending',
              lock_owner TEXT DEFAULT '',
              lock_at TEXT DEFAULT '',
              processed_at TEXT,
              retries INTEGER DEFAULT 0,
              error_msg TEXT,
              sources_list TEXT,
              aliases TEXT,
              last_seen_rss TEXT,
              created_at TIMESTAMPTZ DEFAULT NOW(),
              updated_at TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_raw_status ON raw(status);
            CREATE INDEX IF NOT EXISTS idx_raw_text_hash ON raw(text_hash);

            -- articles_index
            CREATE TABLE IF NOT EXISTS articles_index (
              id BIGSERIAL PRIMARY KEY,
              url_hash TEXT,
              text_hash TEXT,
              article_url_canon TEXT,
              row_id_raw INTEGER,
              first_seen TEXT,
              last_seen TEXT,
              is_duplicate TEXT,
              reason TEXT,
              language TEXT,
              category_guess TEXT,
              rev_n INTEGER,
              created_at TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_articles_url_hash ON articles_index(url_hash);
            CREATE INDEX IF NOT EXISTS idx_articles_text_hash ON articles_index(text_hash);

            -- diagnostics
            CREATE TABLE IF NOT EXISTS diagnostics (
              id BIGSERIAL PRIMARY KEY,
              ts TIMESTAMPTZ DEFAULT NOW(),
              level TEXT,
              component TEXT,
              message TEXT,
              details JSONB
            );

            -- config
            CREATE TABLE IF NOT EXISTS config (
              k TEXT PRIMARY KEY,
              v TEXT
            );
            """
            
            cur.execute(schema_sql)
            print("✅ Новая схема создана!")
            
            # Добавляем базовую конфигурацию
            cur.execute("INSERT INTO config (k, v) VALUES (%s, %s) ON CONFLICT (k) DO UPDATE SET v = EXCLUDED.v", 
                       ("schema_version", "v1_fixed"))
            cur.execute("INSERT INTO config (k, v) VALUES (%s, %s) ON CONFLICT (k) DO UPDATE SET v = EXCLUDED.v", 
                       ("created_or_migrated_at", "2025-08-25"))
            
            print("✅ Базовая конфигурация добавлена")
        
        conn.close()
        print("✅ Соединение закрыто")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка исправления схемы: {e}")
        return False

def test_fixed_schema():
    """Тестирует исправленную схему"""
    print("\n🧪 Тестируем исправленную схему...")
    
    try:
        from pg_client import PgClient
        client = PgClient()
        
        # Тест upsert_feed
        test_feed = {
            "feed_url": "https://test.example.com/rss.xml",
            "feed_url_canon": "https://test.example.com/rss.xml",
            "lang": "en",
            "status": "active",
            "last_entry_date": "",
            "last_crawled": "",
            "no_updates_days": 0,
            "etag": "",
            "last_modified": "",
            "health_score": "100",
            "notes": "test feed",
            "checked_at": ""
        }
        
        client.upsert_feed(test_feed)
        print("✅ upsert_feed работает")
        
        # Тест get_active_feeds
        feeds = client.get_active_feeds()
        print(f"✅ get_active_feeds работает: {len(feeds)} фидов")
        
        # Тест raw операций
        test_raw = {
            "source": "test",
            "feed_url": "https://test.example.com/rss.xml",
            "article_url": "https://test.example.com/article1",
            "article_url_canon": "https://test.example.com/article1",
            "url_hash": "testhash123",
            "text_hash": "",
            "status": "pending",
            "lock_owner": "",
            "found_at": "2025-08-25",
            "fetched_at": "",
            "published_at": "",
            "language": "",
            "title": "",
            "subtitle": "",
            "authors": "",
            "section": "",
            "tags": "",
            "article_type": "",
            "clean_text": "",
            "clean_text_len": 0,
            "full_text_ref": "",
            "full_text_len": 0,
            "word_count": 0,
            "out_links": "",
            "category_guess": "",
            "lock_at": "",
            "processed_at": "",
            "retries": 0,
            "error_msg": "",
            "sources_list": "",
            "aliases": "",
            "last_seen_rss": ""
        }
        
        row_id = client.append_raw_minimal(test_raw)
        print(f"✅ append_raw_minimal работает: row_id = {row_id}")
        
        # Тест get_pending_raw_rows
        pending = client.get_pending_raw_rows(5)
        print(f"✅ get_pending_raw_rows работает: {len(pending)} pending")
        
        client.close()
        return True
        
    except Exception as e:
        print(f"❌ Ошибка тестирования схемы: {e}")
        return False

def main():
    print("🔧 ИСПРАВЛЕНИЕ СХЕМЫ POSTGRESQL")
    print("=" * 50)
    
    if not fix_schema():
        print("❌ Не удалось исправить схему")
        return 1
    
    if not test_fixed_schema():
        print("❌ Тест исправленной схемы провален")
        return 1
    
    print("\n🎉 СХЕМА ИСПРАВЛЕНА И ПРОТЕСТИРОВАНА!")
    print("🚀 Теперь можно запускать полный тест:")
    print("   python test_railway.py")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())