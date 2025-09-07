#!/usr/bin/env python3
"""
Check which NYTimes feeds are already in the database
"""

import os
from pg_client_new import PgClient

# List of NYTimes feeds to check
nytimes_feeds = [
    "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/US.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/Sports.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/Science.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/Health.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/Politics.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/Upshot.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/Economy.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/Arts.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/Style.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/Travel.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/SmallBusiness.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/YourMoney.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/MediaandAdvertising.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/Movies.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/Music.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/Television.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/Theater.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/Books.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/FashionandStyle.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/DiningandWine.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/TMagazine.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/Obituaries.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/RealEstate.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/Automobiles.xml"
]

def main():
    # Require PG_DSN to be provided via environment
    if not os.environ.get('PG_DSN'):
        print("❌ PG_DSN is not set. Please export PG_DSN before running.")
        print("   Example: export PG_DSN=postgresql://user:pass@host:5432/dbname")
        return 1

    client = PgClient()
    
    try:
        # Get all feeds from database
        with client.conn.cursor() as cur:
            cur.execute("SELECT feed_url, status FROM feeds ORDER BY feed_url")
            existing_feeds = {row[0]: row[1] for row in cur.fetchall()}
        
        print("=== NYTimes Feeds Check ===")
        print(f"Total feeds in database: {len(existing_feeds)}")
        print()
        
        found = []
        missing = []
        
        for feed_url in nytimes_feeds:
            if feed_url in existing_feeds:
                status = existing_feeds[feed_url]
                found.append((feed_url, status))
                print(f"✓ FOUND: {feed_url} (status: {status})")
            else:
                missing.append(feed_url)
                print(f"✗ MISSING: {feed_url}")
        
        print()
        print("=== Summary ===")
        print(f"NYTimes feeds found: {len(found)}")
        print(f"NYTimes feeds missing: {len(missing)}")
        print()
        
        if missing:
            print("Missing feeds:")
            for feed_url in missing:
                print(f"  - {feed_url}")
        
        print()
        print("=== Other feeds in database ===")
        other_feeds = [url for url in existing_feeds.keys() if not any(nyt in url for nyt in ["nytimes.com"])]
        for feed_url in other_feeds:
            print(f"  - {feed_url} (status: {existing_feeds[feed_url]})")
            
    finally:
        client.close()

if __name__ == "__main__":
    main()
