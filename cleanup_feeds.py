import sqlite3
import feedparser
import logging
import requests

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',
    handlers=[
        logging.FileHandler("feed_cleanup.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

DB_PATH = r"D:\Articles\SQLite\rag.db"
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

def cleanup_feeds():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Get all feeds
        cursor.execute("SELECT id, url FROM feeds")
        feeds = cursor.fetchall()
        
        logger.info(f"🔍 Checking {len(feeds)} feeds for validity...")
        logger.info("-" * 60)
        
        deleted_count = 0
        kept_count = 0
        
        for feed_id, url in feeds:
            should_delete = False
            reason = ""
            
            try:
                # 1. Check network connectivity first
                try:
                    resp = requests.get(url, headers=HEADERS, timeout=10)
                    if resp.status_code != 200:
                        should_delete = True
                        reason = f"HTTP {resp.status_code}"
                except Exception as e:
                    should_delete = True
                    reason = f"Network Error: {str(e)[:50]}"
                
                if not should_delete:
                    # 2. Parse Feed
                    parsed = feedparser.parse(url)
                    
                    if not parsed.entries:
                        # If no entries, check if it's a valid feed structure at least
                        if parsed.bozo and not parsed.feed:
                            should_delete = True
                            reason = "Invalid Format & No Entries"
                        elif not parsed.feed.get('title'):
                             should_delete = True
                             reason = "Empty Feed (No Title/Entries)"
                        else:
                            # It has a title but no entries. 
                            # User said "does not have data". 
                            # We'll be strict: if 0 entries, we consider it "no data" for now.
                            should_delete = True
                            reason = "No Entries Found"
            
            except Exception as e:
                should_delete = True
                reason = f"Exception: {e}"
            
            if should_delete:
                logger.info(f"❌ Deleting {url}")
                logger.info(f"   Reason: {reason}")
                cursor.execute("DELETE FROM feeds WHERE id = ?", (feed_id,))
                deleted_count += 1
            else:
                logger.info(f"✅ Active: {url}")
                kept_count += 1
                
        conn.commit()
        conn.close()
        
        logger.info("-" * 60)
        logger.info(f"🎉 Cleanup Complete")
        logger.info(f"🗑️  Deleted: {deleted_count}")
        logger.info(f"✅ Kept: {kept_count}")
        logger.info(f"📊 Remaining Feeds: {kept_count}")

    except Exception as e:
        logger.error(f"Cleanup failed: {e}")

if __name__ == "__main__":
    cleanup_feeds()
