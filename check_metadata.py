"""
Check metadata completeness in the database
"""
import sqlite3
import json
from pprint import pprint

# Connect to database
conn = sqlite3.connect(r'D:\Articles\SQLite\rag.db')
cursor = conn.cursor()

# Get the most recently updated articles
cursor.execute("""
    SELECT id, title, meta, updated_at 
    FROM articles 
    WHERE status = 'processed'
    ORDER BY updated_at DESC 
    LIMIT 5
""")

articles = cursor.fetchall()

print("=" * 80)
print("CHECKING METADATA COMPLETENESS FOR RECENTLY PROCESSED ARTICLES")
print("=" * 80)

for article_id, title, meta_json, updated_at in articles:
    print(f"\n📰 Article ID: {article_id}")
    print(f"   Title: {title[:60]}...")
    print(f"   Updated: {updated_at}")
    
    if meta_json:
        meta = json.loads(meta_json)
        
        # Check for key fields
        print(f"\n   📊 Metadata fields present:")
        print(f"      - Authors: {meta.get('authors', [])}")
        print(f"      - Keywords: {len(meta.get('keywords', []))} keywords")
        print(f"      - Images: {len(meta.get('images', []))} images")
        print(f"      - Top Image: {meta.get('top_image', 'N/A')[:50] if meta.get('top_image') else 'N/A'}")
        print(f"      - Videos: {len(meta.get('videos', []))} videos")
        print(f"      - Publisher: {meta.get('publisher', 'N/A')}")
        print(f"      - Section: {meta.get('section', 'N/A')}")
        print(f"      - Language: {meta.get('language', 'N/A')}")
        print(f"      - Word Count: {meta.get('word_count', 'N/A')}")
        print(f"      - Published At: {meta.get('published_at', 'N/A')}")
        
        # Show all keys
        print(f"\n   🔑 All metadata keys ({len(meta.keys())} total):")
        print(f"      {', '.join(sorted(meta.keys()))}")
    else:
        print("   ⚠️  No metadata found!")
    
    print("-" * 80)

conn.close()

print("\n✅ Verification complete!")
