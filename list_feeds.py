import sqlite3
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

DB_PATH = r"D:\Articles\SQLite\rag.db"

def list_feeds():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("SELECT id, url, status, last_checked FROM feeds")
        feeds = cursor.fetchall()
        
        print("=" * 80)
        print(f"📡 RSS Feeds in Database ({len(feeds)} total)")
        print("=" * 80)
        
        if not feeds:
            print("No feeds found.")
        
        for feed in feeds:
            fid, url, status, last_checked = feed
            status_icon = "✅" if status == 'active' else "❌"
            print(f"{status_icon} [{fid}] {url}")
            if last_checked:
                print(f"   🕒 Last checked: {last_checked}")
            print("-" * 40)
            
        conn.close()
        
    except Exception as e:
        logger.error(f"Failed to list feeds: {e}")

if __name__ == "__main__":
    list_feeds()
