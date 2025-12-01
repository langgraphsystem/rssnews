import sqlite3
import logging

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

DB_PATH = r"D:\Articles\SQLite\rag.db"
FEEDS_FILE = "all_feeds.txt"

def import_feeds():
    try:
        # Read feeds from file
        with open(FEEDS_FILE, "r", encoding="utf-8") as f:
            feeds = [line.strip() for line in f.readlines() if line.strip()]
            
        if not feeds:
            print("❌ No feeds found in file.")
            return

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        print(f"📦 Importing {len(feeds)} feeds into database...")
        print("-" * 60)
        
        added_count = 0
        existing_count = 0
        
        for url in feeds:
            try:
                # Check if exists
                cursor.execute("SELECT id FROM feeds WHERE url = ?", (url,))
                if cursor.fetchone():
                    existing_count += 1
                else:
                    cursor.execute("INSERT INTO feeds (url, status) VALUES (?, 'active')", (url,))
                    added_count += 1
                    print(f"✅ Added: {url}")
            except Exception as e:
                print(f"❌ Error adding {url}: {e}")
                
        conn.commit()
        conn.close()
        
        print("-" * 60)
        print(f"🎉 Import complete!")
        print(f"✅ Added: {added_count}")
        print(f"⚠️  Skipped (already exists): {existing_count}")
        print(f"📊 Total feeds in DB: {existing_count + added_count}")

    except Exception as e:
        logger.error(f"Failed to import feeds: {e}")

if __name__ == "__main__":
    import_feeds()
