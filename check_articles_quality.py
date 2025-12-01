"""
Check quality of saved articles in SQLite database
"""
import sqlite3
import json
from datetime import datetime

DB_PATH = "D:/Articles/SQLite/rag.db"

def check_articles_quality():
    """Check and display article quality metrics"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    print("=" * 80)
    print("📊 ARTICLE QUALITY CHECK")
    print("=" * 80)
    
    # Overall stats
    cursor.execute("SELECT COUNT(*) as total FROM articles")
    total = cursor.fetchone()['total']
    print(f"\n✅ Total articles: {total}")
    
    cursor.execute("SELECT COUNT(*) as pending FROM articles WHERE status = 'pending'")
    pending = cursor.fetchone()['pending']
    print(f"⏳ Pending: {pending}")
    
    cursor.execute("SELECT COUNT(*) as processed FROM articles WHERE status = 'processed'")
    processed = cursor.fetchone()['processed']
    print(f"✅ Processed: {processed}")
    
    # Content length stats
    cursor.execute("""
        SELECT 
            AVG(LENGTH(content)) as avg_length,
            MIN(LENGTH(content)) as min_length,
            MAX(LENGTH(content)) as max_length
        FROM articles
    """)
    stats = cursor.fetchone()
    print(f"\n📝 Content Length Statistics:")
    print(f"   Average: {stats['avg_length']:.0f} characters")
    print(f"   Min: {stats['min_length']} characters")
    print(f"   Max: {stats['max_length']} characters")
    
    # Articles with no content
    cursor.execute("SELECT COUNT(*) as empty FROM articles WHERE LENGTH(content) < 50")
    empty = cursor.fetchone()['empty']
    print(f"\n⚠️  Articles with little/no content (<50 chars): {empty}")
    
    # Sample articles
    print("\n" + "=" * 80)
    print("📰 SAMPLE ARTICLES (First 5)")
    print("=" * 80)
    
    cursor.execute("""
        SELECT id, url, title, content, created_at, meta 
        FROM articles 
        ORDER BY id 
        LIMIT 5
    """)
    
    for i, row in enumerate(cursor.fetchall(), 1):
        print(f"\n[{i}] Article ID: {row['id']}")
        print(f"    Title: {row['title'][:70]}...")
        print(f"    URL: {row['url'][:70]}...")
        print(f"    Content length: {len(row['content'])} chars")
        print(f"    Created: {row['created_at']}")
        
        # Parse metadata
        try:
            meta = json.loads(row['meta'])
            if 'published_at' in meta:
                print(f"    Published: {meta['published_at']}")
        except:
            pass
        
        # Show content preview
        content_preview = row['content'][:200].replace('\n', ' ')
        print(f"    Preview: {content_preview}...")
    
    # Check for duplicates by URL
    print("\n" + "=" * 80)
    print("🔍 DUPLICATE CHECK")
    print("=" * 80)
    
    cursor.execute("""
        SELECT url, COUNT(*) as count 
        FROM articles 
        GROUP BY url 
        HAVING count > 1
    """)
    
    duplicates = cursor.fetchall()
    if duplicates:
        print(f"\n⚠️  Found {len(duplicates)} duplicate URLs:")
        for dup in duplicates[:5]:
            print(f"   - {dup['url'][:60]}... (x{dup['count']})")
    else:
        print("\n✅ No duplicate URLs found")
    
    # Check metadata quality
    print("\n" + "=" * 80)
    print("📋 METADATA QUALITY")
    print("=" * 80)
    
    cursor.execute("SELECT meta FROM articles LIMIT 100")
    
    has_published_date = 0
    has_title = 0
    total_checked = 0
    
    for row in cursor.fetchall():
        total_checked += 1
        try:
            meta = json.loads(row['meta'])
            if meta.get('published_at'):
                has_published_date += 1
            if meta.get('title'):
                has_title += 1
        except:
            pass
    
    print(f"\nChecked {total_checked} articles:")
    print(f"   ✅ With published date: {has_published_date} ({has_published_date/total_checked*100:.1f}%)")
    print(f"   ✅ With title: {has_title} ({has_title/total_checked*100:.1f}%)")
    
    # Check feeds
    print("\n" + "=" * 80)
    print("📡 FEED STATISTICS")
    print("=" * 80)
    
    cursor.execute("SELECT COUNT(*) as total FROM feeds")
    total_feeds = cursor.fetchone()['total']
    print(f"\n✅ Total feeds: {total_feeds}")
    
    cursor.execute("SELECT COUNT(*) as active FROM feeds WHERE status = 'active'")
    active_feeds = cursor.fetchone()['active']
    print(f"✅ Active feeds: {active_feeds}")
    
    conn.close()
    
    print("\n" + "=" * 80)
    print("✅ Quality check complete!")
    print("=" * 80)

if __name__ == "__main__":
    check_articles_quality()
