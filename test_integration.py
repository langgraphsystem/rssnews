#!/usr/bin/env python3
"""
Integration test for the RSS news aggregation system
Tests the complete pipeline: polling -> queuing -> processing
"""

import os
import sys
import logging
from datetime import datetime, timezone

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pg_client_new import PgClient
from rss.poller import RSSPoller
from worker import ArticleWorker

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

def run_integration_test():
    """Run integration test of the complete pipeline"""
    
    print("=== RSS News Integration Test ===")
    
    # Initialize database
    print("1. Initializing database...")
    try:
        db = PgClient()
        db.ensure_schema()
        print("✓ Database initialized")
    except Exception as e:
        print(f"✗ Database initialization failed: {e}")
        return False
    
    # Add test feeds
    print("\n2. Adding test feeds...")
    test_feeds = [
        "https://feeds.bbci.co.uk/news/rss.xml",
        "https://rss.cnn.com/rss/edition.rss"
    ]
    
    added_feeds = 0
    for feed_url in test_feeds:
        try:
            feed_id = db.insert_feed(feed_url, lang='en', category='news')
            if feed_id:
                print(f"✓ Added: {feed_url}")
                added_feeds += 1
            else:
                print(f"~ Already exists: {feed_url}")
                added_feeds += 1
        except Exception as e:
            print(f"✗ Failed to add {feed_url}: {e}")
    
    if added_feeds == 0:
        print("✗ No feeds added")
        return False
    
    # Test RSS polling
    print(f"\n3. Testing RSS polling ({added_feeds} feeds)...")
    try:
        poller = RSSPoller(db, batch_size=5, max_workers=3)
        poll_stats = poller.poll_active_feeds(feed_limit=2)  # Test with limited feeds
        poller.close()
        
        print(f"✓ Polling complete:")
        print(f"  Feeds processed: {poll_stats['feeds_polled']}")
        print(f"  New articles: {poll_stats['new_articles']}")
        print(f"  Errors: {poll_stats['feeds_errors']}")
        
        if poll_stats['new_articles'] == 0:
            print("! No new articles found (feeds may be cached)")
            
    except Exception as e:
        print(f"✗ Polling failed: {e}")
        return False
    
    # Test article processing
    print("\n4. Testing article processing...")
    try:
        worker = ArticleWorker(db, batch_size=10, max_workers=3)
        work_stats = worker.process_pending_articles()
        worker.close()
        
        print(f"✓ Processing complete:")
        print(f"  Articles processed: {work_stats['articles_processed']}")
        print(f"  Successful: {work_stats['successful']}")
        print(f"  Duplicates: {work_stats['duplicates']}")
        print(f"  Errors: {work_stats['errors']}")
        
    except Exception as e:
        print(f"✗ Processing failed: {e}")
        return False
    
    # Check final statistics
    print("\n5. Final system statistics...")
    try:
        stats = db.get_stats()
        print(f"✓ System stats:")
        print(f"  Active feeds: {stats.get('active_feeds', 0)}")
        print(f"  Total articles: {stats.get('total_articles', 0)}")
        print(f"  Articles (24h): {stats.get('articles_24h', 0)}")
        
        if stats.get('articles'):
            print("  Article status breakdown:")
            for status, count in stats['articles'].items():
                print(f"    {status}: {count}")
                
    except Exception as e:
        print(f"✗ Stats retrieval failed: {e}")
        return False
    
    # Cleanup
    db.close()
    
    print("\n=== Integration Test Complete ===")
    print("✓ All components working correctly")
    return True

def run_smoke_test():
    """Run a quick smoke test of core components"""
    
    print("=== Quick Smoke Test ===")
    
    # Test database connection
    print("Testing database connection...")
    try:
        db = PgClient()
        stats = db.get_stats()
        db.close()
        print("✓ Database connection OK")
    except Exception as e:
        print(f"✗ Database connection failed: {e}")
        return False
    
    # Test HTTP client
    print("Testing HTTP client...")
    try:
        from net.http import HttpClient
        http = HttpClient()
        response, final_url, cached = http.get_with_conditional_headers(
            "https://httpbin.org/get"
        )
        http.close()
        
        if response and response.status_code == 200:
            print("✓ HTTP client OK")
        else:
            print("✗ HTTP client failed")
            return False
    except Exception as e:
        print(f"✗ HTTP client failed: {e}")
        return False
    
    # Test parser
    print("Testing content parser...")
    try:
        from parser.extract import extract_all
        
        test_html = """
        <html>
            <head>
                <title>Test Article</title>
                <meta name="description" content="Test description">
            </head>
            <body>
                <article>
                    <h1>Test Article</h1>
                    <p>This is test content for parsing.</p>
                </article>
            </body>
        </html>
        """
        
        parsed = extract_all(test_html, "https://example.com/test")
        
        if parsed.title and parsed.full_text:
            print("✓ Content parser OK")
        else:
            print("✗ Content parser failed")
            return False
    except Exception as e:
        print(f"✗ Content parser failed: {e}")
        return False
    
    print("✓ Smoke test passed")
    return True

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="RSS News Integration Test")
    parser.add_argument("--smoke", action="store_true", 
                       help="Run quick smoke test only")
    parser.add_argument("--full", action="store_true",
                       help="Run full integration test")
    
    args = parser.parse_args()
    
    success = True
    
    if args.smoke or not args.full:
        success = run_smoke_test()
    
    if args.full and success:
        success = run_integration_test()
    
    if success:
        print("\n🎉 All tests passed!")
        sys.exit(0)
    else:
        print("\n❌ Tests failed!")
        sys.exit(1)