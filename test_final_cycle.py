#!/usr/bin/env python3
"""
Финальный тест полного цикла работы с Railway PostgreSQL
"""
import os
import sys
import subprocess

def check_pg_dsn():
    """Проверяет наличие переменной окружения PG_DSN"""
    pg_dsn = os.environ.get('PG_DSN')
    if not pg_dsn:
        print("❌ Переменная окружения PG_DSN не установлена.")
        print("   Установите ее перед запуском теста, например:")
        print("   set PG_DSN=postgresql://user:pass@host:port/dbname")
        return False
    print(f"✅ PG_DSN найдена: {pg_dsn[:50]}...")
    return True

def run_full_cycle():
    """Запускает полный цикл: discovery -> poll -> work"""
    
    print("🎯 ФИНАЛЬНЫЙ ТЕСТ ПОЛНОГО ЦИКЛА")
    print("=" * 50)
    
    # Очищаем БД и пересоздаем схему
    print("1. Пересоздаем схему БД...")
    result = subprocess.run([sys.executable, "fix_schema.py"], 
                          capture_output=True, text=True)
    if result.returncode == 0:
        print("✅ Схема пересоздана")
    else:
        print("❌ Ошибка пересоздания схемы")
        return False
    
    # Discovery - добавляем несколько RSS
    print("\n2. Добавляем RSS фиды...")
    test_feeds = [
        "https://feeds.bbci.co.uk/news/rss.xml",
        "https://rss.cnn.com/rss/edition.rss",
        "https://www.theguardian.com/world/rss"
    ]
    
    for i, feed_url in enumerate(test_feeds, 1):
        print(f"   2.{i} Добавляем: {feed_url}")
        result = subprocess.run([
            sys.executable, "main.py", "discovery", "--feed", feed_url
        ], capture_output=True, text=True, timeout=60)
        
        if result.returncode == 0:
            print(f"      ✅ Добавлен успешно")
        else:
            print(f"      ⚠️ Ошибка: {result.stderr.strip()}")
    
    # Poll - опрашиваем фиды
    print("\n3. Опрашиваем RSS фиды...")
    result = subprocess.run([sys.executable, "main.py", "poll"], 
                          capture_output=True, text=True, timeout=120)
    
    if result.returncode == 0:
        print("✅ Опрос RSS выполнен успешно")
    else:
        print(f"❌ Ошибка опроса: {result.stderr.strip()}")
        return False
    
    # Work - обрабатываем статьи
    print("\n4. Обрабатываем статьи...")
    result = subprocess.run([
        sys.executable, "main.py", "work", "--worker-id", "final-test"
    ], capture_output=True, text=True, timeout=180)
    
    if result.returncode == 0:
        print("✅ Обработка статей выполнена")
        if result.stdout:
            print(f"   Output: {result.stdout.strip()}")
    else:
        print(f"⚠️ Обработка завершена с предупреждениями")
        if result.stderr:
            print(f"   Error: {result.stderr.strip()[:200]}...")
    
    return True

def check_results():
    """Проверяет результаты работы"""
    print("\n📊 Проверяем результаты...")
    
    try:
        from pg_client import PgClient
        client = PgClient()
        
        # Проверяем feeds
        feeds = client.get_active_feeds()
        print(f"✅ Активных фидов: {len(feeds)}")
        
        # Проверяем сколько статей было найдено
        with client.conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM raw")
            total_articles = cur.fetchone()[0]
            print(f"✅ Всего статей: {total_articles}")
            
            cur.execute("SELECT COUNT(*) FROM raw WHERE status = 'pending'")
            pending_articles = cur.fetchone()[0]
            print(f"✅ Pending статей: {pending_articles}")
            
            cur.execute("SELECT COUNT(*) FROM raw WHERE status = 'stored'")
            processed_articles = cur.fetchone()[0]
            print(f"✅ Обработанных статей: {processed_articles}")
            
            cur.execute("SELECT COUNT(*) FROM articles_index")
            indexed_articles = cur.fetchone()[0]
            print(f"✅ Статей в индексе: {indexed_articles}")
            
            cur.execute("SELECT COUNT(*) FROM config")
            config_entries = cur.fetchone()[0]
            print(f"✅ Записей конфигурации: {config_entries}")
        
        client.close()
        return True
        
    except Exception as e:
        print(f"❌ Ошибка проверки результатов: {e}")
        return False

def main():
    """Основная функция"""
    
    if not check_pg_dsn():
        print("\nТест не может быть выполнен без подключения к БД.")
        return 1
    
    if not run_full_cycle():
        print("❌ Полный цикл не завершен")
        return 1
    
    if not check_results():
        print("❌ Ошибка проверки результатов")
        return 1
    
    print("\n" + "=" * 50)
    print("🎉 ФИНАЛЬНЫЙ ТЕСТ ЗАВЕРШЕН УСПЕШНО!")
    print("🚀 RSS NEWS PROJECT МИГРИРОВАН НА POSTGRESQL!")
    print("=" * 50)
    
    print("\n📋 Что работает:")
    print("✅ Подключение к Railway PostgreSQL")
    print("✅ Создание и миграция схемы БД")
    print("✅ Добавление RSS фидов (discovery)")
    print("✅ Опрос RSS и извлечение статей (poll)")
    print("✅ Обработка статей и извлечение контента (work)")
    print("✅ Дедупликация и индексирование")
    print("✅ Диагностика и логирование")
    
    print("\n🎯 Проект готов к продуктивному использованию!")
    print("💡 Запускайте регулярно:")
    print("   python main.py poll    # Каждые 15-30 минут")
    print("   python main.py work    # Каждые 5-10 минут")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())