"""
Проверка полного текста статьи из базы данных
"""
import sqlite3

conn = sqlite3.connect(r'D:\Articles\SQLite\rag.db')
cursor = conn.cursor()

# Получаем последнюю обработанную статью
cursor.execute("""
    SELECT id, url, title, content 
    FROM articles 
    WHERE status = 'processed' AND content IS NOT NULL AND content != ''
    ORDER BY updated_at DESC 
    LIMIT 1
""")

row = cursor.fetchone()
if row:
    article_id, url, title, content = row
    
    print("=" * 80)
    print("ПОЛНЫЙ ТЕКСТ СТАТЬИ ИЗ БАЗЫ ДАННЫХ")
    print("=" * 80)
    print(f"\nID: {article_id}")
    print(f"URL: {url}")
    print(f"Заголовок: {title}")
    print(f"\nДлина текста: {len(content)} символов")
    print(f"Количество слов: ~{len(content.split())}")
    print("\n" + "=" * 80)
    print("ПОЛНЫЙ ТЕКСТ:")
    print("=" * 80)
    print(content)
    print("\n" + "=" * 80)
    print("КОНЕЦ ТЕКСТА")
    print("=" * 80)
else:
    print("❌ Не найдено обработанных статей с текстом!")

conn.close()
