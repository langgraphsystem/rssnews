"""
Comprehensive RSS Feed Collection - 150+ feeds
Organized by category: News, Technology, Business, Sports, Science, Entertainment
"""
import sys
from local_storage import LocalStorageClient
import config

# Initialize local storage
cfg = config.load_config()
storage = LocalStorageClient(cfg['sqlite_db_path'], cfg['chroma_db_path'])

# Comprehensive feed list
FEEDS = [
    # === NEWS - GENERAL (25 feeds) ===
    ("https://feeds.bbci.co.uk/news/rss.xml", "en", "news"),
    ("https://feeds.bbci.co.uk/news/world/rss.xml", "en", "world"),
    ("https://feeds.bbci.co.uk/news/uk/rss.xml", "en", "uk"),
    ("https://feeds.bbci.co.uk/news/business/rss.xml", "en", "business"),
    ("https://feeds.bbci.co.uk/news/politics/rss.xml", "en", "politics"),
    ("https://feeds.bbci.co.uk/news/health/rss.xml", "en", "health"),
    ("https://feeds.bbci.co.uk/news/education/rss.xml", "en", "education"),
    ("https://feeds.bbci.co.uk/news/science_and_environment/rss.xml", "en", "science"),
    ("https://feeds.bbci.co.uk/news/technology/rss.xml", "en", "technology"),
    ("https://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml", "en", "entertainment"),
    
    ("http://rss.cnn.com/rss/cnn_topstories.rss", "en", "news"),
    ("http://rss.cnn.com/rss/cnn_world.rss", "en", "world"),
    ("http://rss.cnn.com/rss/cnn_us.rss", "en", "us"),
    ("http://rss.cnn.com/rss/money_latest.rss", "en", "business"),
    ("http://rss.cnn.com/rss/cnn_tech.rss", "en", "technology"),
    ("http://rss.cnn.com/rss/cnn_health.rss", "en", "health"),
    ("http://rss.cnn.com/rss/cnn_showbiz.rss", "en", "entertainment"),
    ("http://rss.cnn.com/rss/cnn_travel.rss", "en", "travel"),
    
    ("https://www.theguardian.com/world/rss", "en", "world"),
    ("https://www.theguardian.com/uk/rss", "en", "uk"),
    ("https://www.theguardian.com/us-news/rss", "en", "us"),
    ("https://www.theguardian.com/business/rss", "en", "business"),
    ("https://www.theguardian.com/technology/rss", "en", "technology"),
    ("https://www.theguardian.com/science/rss", "en", "science"),
    ("https://www.theguardian.com/environment/rss", "en", "environment"),
    
    # === TECHNOLOGY (30 feeds) ===
    ("https://techcrunch.com/feed/", "en", "technology"),
    ("https://techcrunch.com/category/startups/feed/", "en", "startups"),
    ("https://techcrunch.com/category/apps/feed/", "en", "apps"),
    ("https://techcrunch.com/category/gadgets/feed/", "en", "gadgets"),
    ("https://techcrunch.com/category/artificial-intelligence/feed/", "en", "ai"),
    
    ("https://www.theverge.com/rss/index.xml", "en", "technology"),
    ("https://www.theverge.com/tech/rss/index.xml", "en", "tech"),
    ("https://www.theverge.com/apple/rss/index.xml", "en", "apple"),
    ("https://www.theverge.com/google/rss/index.xml", "en", "google"),
    ("https://www.theverge.com/microsoft/rss/index.xml", "en", "microsoft"),
    
    ("https://www.wired.com/feed/rss", "en", "technology"),
    ("https://www.wired.com/feed/category/business/latest/rss", "en", "business"),
    ("https://www.wired.com/feed/category/gear/latest/rss", "en", "gadgets"),
    ("https://www.wired.com/feed/category/science/latest/rss", "en", "science"),
    ("https://www.wired.com/feed/category/security/latest/rss", "en", "security"),
    
    ("http://feeds.arstechnica.com/arstechnica/index", "en", "technology"),
    ("http://feeds.arstechnica.com/arstechnica/technology-lab", "en", "tech-lab"),
    ("http://feeds.arstechnica.com/arstechnica/gadgets", "en", "gadgets"),
    ("http://feeds.arstechnica.com/arstechnica/science", "en", "science"),
    
    ("https://www.engadget.com/rss.xml", "en", "technology"),
    ("https://www.cnet.com/rss/news/", "en", "technology"),
    ("https://www.zdnet.com/news/rss.xml", "en", "technology"),
    ("https://www.techmeme.com/feed.xml", "en", "technology"),
    ("https://www.theinformation.com/feed", "en", "technology"),
    ("https://www.recode.net/rss/index.xml", "en", "technology"),
    ("https://venturebeat.com/feed/", "en", "technology"),
    ("https://www.geekwire.com/feed/", "en", "technology"),
    ("https://siliconangle.com/feed/", "en", "technology"),
    ("https://9to5mac.com/feed/", "en", "apple"),
    ("https://www.macrumors.com/feed/", "en", "apple"),
    
    # === BUSINESS & FINANCE (25 feeds) ===
    ("https://feeds.bloomberg.com/markets/news.rss", "en", "markets"),
    ("https://feeds.bloomberg.com/technology/news.rss", "en", "technology"),
    ("https://feeds.bloomberg.com/politics/news.rss", "en", "politics"),
    
    ("https://www.ft.com/?format=rss", "en", "business"),
    ("https://www.wsj.com/xml/rss/3_7085.xml", "en", "business"),
    ("https://www.wsj.com/xml/rss/3_7014.xml", "en", "markets"),
    ("https://www.wsj.com/xml/rss/3_7031.xml", "en", "technology"),
    
    ("https://www.economist.com/the-world-this-week/rss.xml", "en", "business"),
    ("https://www.economist.com/business/rss.xml", "en", "business"),
    ("https://www.economist.com/finance-and-economics/rss.xml", "en", "finance"),
    ("https://www.economist.com/science-and-technology/rss.xml", "en", "science"),
    
    ("https://hbr.org/feed", "en", "business"),
    ("https://www.forbes.com/real-time/feed2/", "en", "business"),
    ("https://www.inc.com/rss/", "en", "business"),
    ("https://www.fastcompany.com/latest/rss", "en", "business"),
    ("https://www.entrepreneur.com/latest.rss", "en", "entrepreneurship"),
    
    ("https://finance.yahoo.com/news/rssindex", "en", "finance"),
    ("https://www.marketwatch.com/rss/topstories", "en", "markets"),
    ("https://www.cnbc.com/id/100003114/device/rss/rss.html", "en", "business"),
    ("https://www.cnbc.com/id/10000664/device/rss/rss.html", "en", "technology"),
    ("https://www.cnbc.com/id/15839135/device/rss/rss.html", "en", "markets"),
    
    ("https://seekingalpha.com/feed.xml", "en", "investing"),
    ("https://www.investing.com/rss/news.rss", "en", "investing"),
    ("https://www.fool.com/feeds/index.aspx", "en", "investing"),
    
    # === YAHOO FEEDS (24 feeds) ===
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
    ("https://yahoo.com/entertainment/rss", "en", "entertainment"),
    
    # === FOX FEEDS (19 feeds) ===
    ("https://moxie.foxnews.com/google-publisher/latest.xml", "en", "news"),
    ("https://moxie.foxnews.com/google-publisher/world.xml", "en", "world"),
    ("https://moxie.foxnews.com/google-publisher/politics.xml", "en", "politics"),
    ("https://moxie.foxnews.com/google-publisher/science.xml", "en", "science"),
    ("https://moxie.foxnews.com/google-publisher/health.xml", "en", "health"),
    ("https://moxie.foxnews.com/google-publisher/sports.xml", "en", "sports"),
    ("https://moxie.foxnews.com/google-publisher/travel.xml", "en", "travel"),
    ("https://moxie.foxnews.com/google-publisher/tech.xml", "en", "technology"),
    ("https://moxie.foxnews.com/google-publisher/opinion.xml", "en", "opinion"),
    ("https://moxie.foxnews.com/google-publisher/us.xml", "en", "us"),
    ("https://moxie.foxnews.com/google-publisher/videos.xml", "en", "video"),
    
    ("https://moxie.foxbusiness.com/google-publisher/latest.xml", "en", "business"),
    ("https://moxie.foxbusiness.com/google-publisher/economy.xml", "en", "economy"),
    ("https://moxie.foxbusiness.com/google-publisher/markets.xml", "en", "markets"),
    ("https://moxie.foxbusiness.com/google-publisher/personal-finance.xml", "en", "finance"),
    ("https://moxie.foxbusiness.com/google-publisher/lifestyle.xml", "en", "lifestyle"),
    ("https://moxie.foxbusiness.com/google-publisher/real-estate.xml", "en", "real-estate"),
    ("https://moxie.foxbusiness.com/google-publisher/technology.xml", "en", "technology"),
    ("https://moxie.foxbusiness.com/google-publisher/videos.xml", "en", "video"),
    
    # === SCIENCE & RESEARCH (15 feeds) ===
    ("https://www.nature.com/nature.rss", "en", "science"),
    ("https://www.science.org/rss/news_current.xml", "en", "science"),
    ("https://www.scientificamerican.com/feed/", "en", "science"),
    ("https://www.newscientist.com/feed/home", "en", "science"),
    ("https://phys.org/rss-feed/", "en", "science"),
    ("https://www.sciencedaily.com/rss/all.xml", "en", "science"),
    ("https://www.space.com/feeds/all", "en", "space"),
    ("https://www.nasa.gov/rss/dyn/breaking_news.rss", "en", "space"),
    ("https://www.livescience.com/feeds/all", "en", "science"),
    ("https://www.popsci.com/feed/", "en", "science"),
    ("https://arstechnica.com/science/feed/", "en", "science"),
    ("https://www.quantamagazine.org/feed/", "en", "science"),
    ("https://www.sciencenews.org/feed", "en", "science"),
    ("https://www.technologyreview.com/feed/", "en", "technology"),
    ("https://spectrum.ieee.org/feeds/feed.rss", "en", "technology"),
    
    # === ENTERTAINMENT & CULTURE (12 feeds) ===
    ("https://www.hollywoodreporter.com/feed/", "en", "entertainment"),
    ("https://variety.com/feed/", "en", "entertainment"),
    ("https://deadline.com/feed/", "en", "entertainment"),
    ("https://ew.com/feed/", "en", "entertainment"),
    ("https://www.rollingstone.com/feed/", "en", "music"),
    ("https://pitchfork.com/rss/reviews/albums/", "en", "music"),
    ("https://www.billboard.com/feed/", "en", "music"),
    ("https://www.vulture.com/feeds/full.xml", "en", "entertainment"),
    ("https://www.avclub.com/rss", "en", "entertainment"),
    ("https://www.polygon.com/rss/index.xml", "en", "gaming"),
    ("https://www.ign.com/feed.xml", "en", "gaming"),
    ("https://kotaku.com/rss", "en", "gaming"),
]

def add_all_feeds():
    """Add all 150+ feeds to local storage"""
    print("=" * 70)
    print("📰 Adding 150+ RSS Feeds to Local Storage")
    print("=" * 70)
    
    total = len(FEEDS)
    added = 0
    existing = 0
    errors = 0
    
    for i, (url, lang, category) in enumerate(FEEDS, 1):
        try:
            feed_id = storage.insert_feed(url, lang, category)
            if feed_id:
                status = "✅ Added" if i > existing else "⚠️  Exists"
                print(f"[{i}/{total}] {status} | {category:20} | {url[:50]}...")
                added += 1
            else:
                print(f"[{i}/{total}] ⚠️  Exists | {category:20} | {url[:50]}...")
                existing += 1
        except Exception as e:
            print(f"[{i}/{total}] ❌ Error | {category:20} | {str(e)[:30]}...")
            errors += 1
    
    print("\n" + "=" * 70)
    print(f"✅ Total feeds: {total}")
    print(f"📊 Added: {added} | Existing: {existing} | Errors: {errors}")
    print("=" * 70)
    
    # Show feed count
    feeds = storage.get_active_feeds()
    print(f"\n📈 Total active feeds in database: {len(feeds)}")


if __name__ == "__main__":
    add_all_feeds()
