#!/usr/bin/env python3
"""
Быстрое исправление проблем с дедупликацией
"""
import os
import sys

# Устанавливаем PG_DSN
if 'PG_DSN' not in os.environ:
    print("❌ Переменная окружения PG_DSN не установлена.")
    print("   Установите ее перед запуском: set PG_DSN=...")
    sys.exit(1)
print("✅ PG_DSN найдена.")

def fix_articles_index_constraint():
    """Исправляет constraint для articles_index"""
    try:
        import psycopg2
        
        conn = psycopg2.connect(os.environ['PG_DSN'])
        conn.autocommit = True
        
        with conn.cursor() as cur:
            print("🔧 Исправляем constraint для articles_index...")
            
            # Удаляем таблицу articles_index и пересоздаем с правильным UNIQUE
            cur.execute("DROP TABLE IF EXISTS articles_index CASCADE")
            
            cur.execute("""
                CREATE TABLE articles_index (
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
                  created_at TIMESTAMPTZ DEFAULT NOW(),
                  UNIQUE(url_hash)
                );
            """)
            
            cur.execute("CREATE INDEX IF NOT EXISTS idx_articles_url_hash ON articles_index(url_hash)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_articles_text_hash ON articles_index(text_hash)")
            
            print("✅ articles_index исправлена с UNIQUE constraint на url_hash")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Ошибка исправления: {e}")
        return False

def main():
    print("🔧 БЫСТРОЕ ИСПРАВЛЕНИЕ ОШИБОК")
    print("=" * 40)
    
    if fix_articles_index_constraint():
        print("✅ Исправления применены!")
        print("\n🚀 Теперь можно запускать:")
        print("   python main.py poll")
        print("   python main.py work")
    else:
        print("❌ Не удалось применить исправления")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())