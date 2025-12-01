import sqlite3
import json
import config

def check_db():
    cfg = config.load_config()
    db_path = cfg['analysis_db_path']
    print(f"📂 Checking Analysis DB: {db_path}")
    
    try:
        conn = sqlite3.connect(db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # 1. Count total articles
        cursor.execute("SELECT count(*) FROM analysis_articles")
        total = cursor.fetchone()[0]
        
        # 2. Count by status
        cursor.execute("SELECT deep_analysis_status, count(*) FROM analysis_articles GROUP BY deep_analysis_status")
        statuses = cursor.fetchall()
        
        print(f"📊 Total Articles: {total}")
        print("📈 Status Breakdown:")
        for status, count in statuses:
            print(f"  - {status}: {count}")
            
        # 3. Show last synced article
        print("\n🔍 Last Synced Article:")
        cursor.execute("SELECT * FROM analysis_articles ORDER BY id DESC LIMIT 1")
        last = cursor.fetchone()
        if last:
            print(f"  ID: {last['id']}")
            print(f"  Original ID: {last['original_id']}")
            print(f"  Title: {last['title']}")
            print(f"  URL: {last['url']}")
            print(f"  Status: {last['deep_analysis_status']}")
            print(f"  Content Length: {len(last['content']) if last['content'] else 0} chars")
        else:
            print("  (No articles found)")
            
        conn.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    check_db()
