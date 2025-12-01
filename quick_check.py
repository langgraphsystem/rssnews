"""
Quick article quality check
"""
import sqlite3
import json

DB_PATH = "D:/Articles/SQLite/rag.db"

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

print("ARTICLE QUALITY CHECK")
print("=" * 60)

# Total count
cursor.execute("SELECT COUNT(*) as total FROM articles")
total = cursor.fetchone()['total']
print(f"\nTotal articles: {total}")

# Sample 3 articles
cursor.execute("SELECT id, title, content, url FROM articles LIMIT 3")
print("\nSample articles:\n")

for row in cursor.fetchall():
    print(f"ID: {row['id']}")
    print(f"Title: {row['title']}")
    print(f"URL: {row['url'][:60]}...")
    print(f"Content: {row['content'][:150]}...")
    print(f"Length: {len(row['content'])} chars")
    print("-" * 60)

conn.close()
