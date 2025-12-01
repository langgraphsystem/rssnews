import sqlite3
import json

conn = sqlite3.connect(r'D:\Articles\SQLite\rag.db')
cursor = conn.cursor()

# Get one processed article
cursor.execute("""
    SELECT id, url, title, content, meta 
    FROM articles 
    WHERE status = 'processed'
    ORDER BY updated_at DESC 
    LIMIT 1
""")

row = cursor.fetchone()
if row:
    article_id, url, title, content, meta_json = row
    
    print("=" * 80)
    print("ПРИМЕР СОХРАНЕННОЙ СТАТЬИ")
    print("=" * 80)
    print(f"\nID: {article_id}")
    print(f"URL: {url}")
    print(f"Title: {title}")
    print(f"\nContent (first 200 chars):\n{content[:200]}...")
    print(f"\nContent length: {len(content)} characters")
    
    if meta_json:
        meta = json.loads(meta_json)
        print(f"\n{'='*80}")
        print("METADATA (JSON):")
        print(f"{'='*80}")
        print(json.dumps(meta, indent=2, ensure_ascii=False))
    else:
        print("\n⚠️ No metadata!")
else:
    print("No processed articles found!")

conn.close()
