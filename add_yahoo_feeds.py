"""
Add Yahoo News and Yahoo Sports/Entertainment RSS feeds to database
"""
import sys
from dotenv import load_dotenv

from pg_client_new import PgClient

# Load environment from .env so PG_DSN is available when run locally
load_dotenv()


# Yahoo feeds (URL, language, category)
YAHOO_FEEDS = [
    # Yahoo News — main + categories
    ("https://news.yahoo.com/rss/", "en", "news"),
    ("https://news.yahoo.com/rss/us", "en", "us"),
    ("https://news.yahoo.com/rss/world", "en", "world"),
    ("https://news.yahoo.com/rss/politics", "en", "politics"),
    ("https://news.yahoo.com/rss/science", "en", "science"),
    ("https://news.yahoo.com/rss/health", "en", "health"),
    ("https://news.yahoo.com/rss/business", "en", "business"),
    ("https://news.yahoo.com/rss/technology", "en", "technology"),
    ("https://news.yahoo.com/rss/entertainment", "en", "entertainment"),
    ("https://news.yahoo.com/rss/lifestyle", "en", "lifestyle"),

    # Yahoo Sports — main + key leagues/sports
    ("https://sports.yahoo.com/rss/", "en", "sports"),
    ("https://sports.yahoo.com/nfl/rss/", "en", "nfl"),
    ("https://sports.yahoo.com/nba/rss/", "en", "nba"),
    ("https://sports.yahoo.com/mlb/rss/", "en", "mlb"),
    ("https://sports.yahoo.com/nhl/rss/", "en", "nhl"),
    ("https://sports.yahoo.com/soccer/rss/", "en", "soccer"),
    ("https://sports.yahoo.com/golf/rss/", "en", "golf"),
    ("https://sports.yahoo.com/tennis/rss/", "en", "tennis"),
    ("https://sports.yahoo.com/nascar/rss/", "en", "nascar"),
    ("https://sports.yahoo.com/mma/rss/", "en", "mma"),
    ("https://sports.yahoo.com/boxing/rss/", "en", "boxing"),
    ("https://sports.yahoo.com/college-football/rss/", "en", "college-football"),
    ("https://sports.yahoo.com/college-basketball/rss/", "en", "college-basketball"),

    # Yahoo Finance — news index RSS
    ("https://finance.yahoo.com/news/rssindex", "en", "finance"),

    # Yahoo Entertainment — legacy root feed (kept)
    ("https://yahoo.com/entertainment/rss", "en", "entertainment-root"),
]


def add_feeds():
    """Add all Yahoo feeds to database"""
    db = PgClient()

    print("=" * 60)
    print("Adding Yahoo RSS feeds (News, Sports, Entertainment)")
    print("=" * 60)

    total_added = 0
    total_existing = 0
    total_errors = 0

    for url, lang, category in YAHOO_FEEDS:
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

    print("\n" + "=" * 60)
    print("Summary:")
    print(f"  ✅ Added:    {total_added}")
    print(f"  ⚠️  Existing: {total_existing}")
    print(f"  ❌ Errors:   {total_errors}")
    print(f"  📊 Total:    {len(YAHOO_FEEDS)}")
    print("=" * 60)

    return total_added > 0 or total_existing > 0


if __name__ == "__main__":
    success = add_feeds()
    sys.exit(0 if success else 1)
