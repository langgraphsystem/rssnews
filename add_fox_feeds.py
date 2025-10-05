"""
Add Fox News and Fox Business RSS feeds to database
"""
import os
import sys
from pg_client_new import PgClient

# Fox News feeds
FOX_NEWS_FEEDS = [
    ("https://moxie.foxnews.com/google-publisher/latest.xml", "en", "news"),
    ("https://moxie.foxnews.com/google-publisher/world.xml", "en", "world"),
    ("https://moxie.foxnews.com/google-publisher/politics.xml", "en", "politics"),
    ("https://moxie.foxnews.com/google-publisher/science.xml", "en", "science"),
    ("https://moxie.foxnews.com/google-publisher/health.xml", "en", "health"),
    ("https://moxie.foxnews.com/google-publisher/sports.xml", "en", "sports"),
    ("https://moxie.foxnews.com/google-publisher/travel.xml", "en", "travel"),
    ("https://moxie.foxnews.com/google-publisher/tech.xml", "en", "technology"),
    ("https://moxie.foxnews.com/google-publisher/opinion.xml", "en", "opinion"),
    ("https://moxie.foxnews.com/google-publisher/videos.xml", "en", "video"),
    ("https://moxie.foxnews.com/google-publisher/us.xml", "en", "us"),
]

# Fox Business feeds
FOX_BUSINESS_FEEDS = [
    ("https://moxie.foxbusiness.com/google-publisher/latest.xml", "en", "business"),
    ("https://moxie.foxbusiness.com/google-publisher/economy.xml", "en", "economy"),
    ("https://moxie.foxbusiness.com/google-publisher/markets.xml", "en", "markets"),
    ("https://moxie.foxbusiness.com/google-publisher/personal-finance.xml", "en", "finance"),
    ("https://moxie.foxbusiness.com/google-publisher/lifestyle.xml", "en", "lifestyle"),
    ("https://moxie.foxbusiness.com/google-publisher/real-estate.xml", "en", "real-estate"),
    ("https://moxie.foxbusiness.com/google-publisher/technology.xml", "en", "technology"),
    ("https://moxie.foxbusiness.com/google-publisher/videos.xml", "en", "video"),
]

def add_feeds():
    """Add all Fox feeds to database"""
    db = PgClient()

    print("=" * 60)
    print("Adding Fox News and Fox Business RSS feeds")
    print("=" * 60)

    total_added = 0
    total_existing = 0
    total_errors = 0

    # Add Fox News feeds
    print("\n📰 Fox News Feeds:")
    print("-" * 60)
    for url, lang, category in FOX_NEWS_FEEDS:
        try:
            feed_id = db.insert_feed(url, lang, category)
            if feed_id:
                print(f"✅ Added: {category:15} | {url}")
                total_added += 1
            else:
                print(f"⚠️  Exists: {category:15} | {url}")
                total_existing += 1
        except Exception as e:
            print(f"❌ Error: {category:15} | {url}")
            print(f"   {e}")
            total_errors += 1

    # Add Fox Business feeds
    print("\n💼 Fox Business Feeds:")
    print("-" * 60)
    for url, lang, category in FOX_BUSINESS_FEEDS:
        try:
            feed_id = db.insert_feed(url, lang, category)
            if feed_id:
                print(f"✅ Added: {category:15} | {url}")
                total_added += 1
            else:
                print(f"⚠️  Exists: {category:15} | {url}")
                total_existing += 1
        except Exception as e:
            print(f"❌ Error: {category:15} | {url}")
            print(f"   {e}")
            total_errors += 1

    # Summary
    print("\n" + "=" * 60)
    print("Summary:")
    print(f"  ✅ Added:    {total_added}")
    print(f"  ⚠️  Existing: {total_existing}")
    print(f"  ❌ Errors:   {total_errors}")
    print(f"  📊 Total:    {len(FOX_NEWS_FEEDS) + len(FOX_BUSINESS_FEEDS)}")
    print("=" * 60)

    # Show current feed count
    try:
        with db._cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM feeds WHERE feed_url LIKE '%foxnews.com%' OR feed_url LIKE '%foxbusiness.com%'")
            fox_count = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM feeds")
            total_count = cur.fetchone()[0]

            print(f"\n📈 Database Stats:")
            print(f"  Fox feeds:   {fox_count}")
            print(f"  Total feeds: {total_count}")
    except Exception as e:
        print(f"❌ Error getting stats: {e}")

    return total_added > 0

if __name__ == "__main__":
    success = add_feeds()
    sys.exit(0 if success else 1)
