"""
Simple RSS news collector for local storage
Polls feeds and saves articles to SQLite
"""
import feedparser
import logging
from datetime import datetime
from local_storage import LocalStorageClient
import config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize storage
cfg = config.load_config()
storage = LocalStorageClient(cfg['sqlite_db_path'], cfg['chroma_db_path'])

def collect_news(max_feeds=None, max_articles_per_feed=20):
    """Collect news from active RSS feeds"""
    logger.info("🚀 Starting news collection...")
    
    # Get active feeds
    feeds = storage.get_active_feeds(limit=max_feeds)
    if not feeds:
        logger.warning("No active feeds found!")
        return
    
    logger.info(f"📡 Polling {len(feeds)} feeds...")
    
    total_new = 0
    total_existing = 0
    
    for i, feed in enumerate(feeds, 1):
        feed_url = feed['url']
        logger.info(f"\n[{i}/{len(feeds)}] Fetching: {feed_url[:60]}...")
        
        try:
            # Parse RSS feed
            parsed = feedparser.parse(feed_url)
            
            if parsed.bozo and not parsed.entries:
                logger.error(f"  ❌ Invalid feed format")
                continue
            
            logger.info(f"  📰 Found {len(parsed.entries)} entries")
            
            # Process entries
            new_count = 0
            for entry in parsed.entries[:max_articles_per_feed]:
                # Extract URL
                url = entry.get('link') or entry.get('id', '')
                if not url or not url.startswith('http'):
                    continue
                
                # Check if exists
                if storage.article_exists(url):
                    total_existing += 1
                    continue

                # Extract metadata
                title = entry.get('title', 'Untitled')
                summary = entry.get('summary', '')
                
                # Try to get publish date
                published_at = None
                for date_field in ['published', 'updated', 'created']:
                    if hasattr(entry, date_field):
                        try:
                            from dateutil import parser as date_parser
                            published_at = date_parser.parse(getattr(entry, date_field))
                            break
                        except:
                            pass
                
                # Prepare article data
                article_data = {
                    'url': url,
                    'title': title,
                    'full_text': summary,  # We'll use summary as initial text
                    'published_at': published_at,
                }
                
                # Insert article
                article_id = storage.insert_article(article_data)
                if article_id:
                    new_count += 1
                    total_new += 1
            
            logger.info(f"  ✅ Added {new_count} new articles")
            
        except Exception as e:
            logger.error(f"  ❌ Error: {str(e)[:50]}")
            continue
    
    logger.info("\n" + "=" * 70)
    logger.info(f"✅ Collection complete!")
    logger.info(f"📊 New articles: {total_new}")
    logger.info(f"⚠️  Existing (skipped): {total_existing}")
    logger.info("=" * 70)
    
    # Show database stats
    pending = storage.get_pending_articles(limit=5)
    logger.info(f"\n📈 Pending articles in database: {len(pending)}")
    if pending:
        logger.info("\nFirst 3 pending articles:")
        for article in pending[:3]:
            logger.info(f"  - {article['title'][:60]}...")

if __name__ == "__main__":
    import sys
    
    # Parse arguments
    # Default to None (all feeds) if not specified
    max_feeds = int(sys.argv[1]) if len(sys.argv) > 1 else None
    max_articles = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    
    logger.info(f"Settings: max_feeds={max_feeds if max_feeds else 'ALL'}, max_articles_per_feed={max_articles}")
    
    collect_news(max_feeds=max_feeds, max_articles_per_feed=max_articles)
