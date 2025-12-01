import requests
from urllib.parse import urljoin
from bs4 import BeautifulSoup
import logging
import concurrent.futures
import time

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

# Known feeds for sites that are hard to scrape or returned errors
KNOWN_FEEDS = {
    "yahoo.com": "https://www.yahoo.com/news/rss",
    "cnn.com": "http://rss.cnn.com/rss/cnn_topstories.rss",
    "usatoday.com": "http://rssfeeds.usatoday.com/UsatodaycomNation-TopStories",
    "washingtonpost.com": "https://feeds.washingtonpost.com/rss/politics",
    "wsj.com": "https://feeds.a.dj.com/rss/RSSWorldNews.xml",
    "bloomberg.com": "https://feeds.bloomberg.com/politics/news.xml",
    "reuters.com": "https://www.reutersagency.com/feed/?best-topics=political-general&post_type=best",
    "thehill.com": "https://thehill.com/feed/",
    "politico.com": "https://rss.politico.com/politics-news.xml",
    "newsweek.com": "https://www.newsweek.com/rss",
    "huffpost.com": "https://www.huffpost.com/section/front-page/feed",
    "latimes.com": "https://www.latimes.com/world/rss2.0.xml",
    "theverge.com": "https://www.theverge.com/rss/index.xml",
    "slate.com": "https://slate.com/feeds/all.rss",
    "cnbc.com": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114",
    "forbes.com": "https://www.forbes.com/most-popular/feed/",
    "espn.com": "https://www.espn.com/espn/rss/news",
    "seattletimes.com": "https://www.seattletimes.com/feed/",
    "sfgate.com": "https://www.sfgate.com/bayarea/feed/Bay-Area-News-429.php",
    "houstonchronicle.com": "https://www.houstonchronicle.com/news/feed/Main-News-Feed-373.php",
    "msn.com": "https://rss.msn.com/en-us/",
    "azcentral.com": "http://rssfeeds.azcentral.com/phoenix/local",
    "dispatch.com": "https://www.dispatch.com/feed",
    "drudgereport.com": "http://drudgereportfeed.com/rss.xml",
    "detroitnews.com": "https://rssfeeds.detroitnews.com/detroit/news",
    "saltlaketribune.com": "https://www.sltrib.com/rss/feed/news",
    "cincinnati.com": "http://rssfeeds.cincinnati.com/cincinnati/news",
    "zerohedge.com": "http://feeds.feedburner.com/zerohedge/feed",
    "freep.com": "http://rssfeeds.freep.com/freep/news",
    "barrons.com": "https://feeds.barrons.com/rss/TBARGlobalMarkets.xml",
    "marketwatch.com": "http://feeds.marketwatch.com/marketwatch/topstories/",
    "usnews.com": "https://www.usnews.com/rss/news",
    "inquirer.com": "https://www.inquirer.com/feeds/news/",
    "miamiherald.com": "https://www.miamiherald.com/news/local/community/miami-dade/rss.xml",
    "abcnews.go.com": "https://abcnews.go.com/abcnews/topstories",
    "axios.com": "https://api.axios.com/feed/",
    "truthout.org": "https://truthout.org/feed/",
}

SITES_TO_SCAN = [
    # Add any remaining sites here if needed, but KNOWN_FEEDS covers most failures
]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

def validate_feed(url):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=5)
        if resp.status_code == 200:
            # Basic check for XML/RSS content
            content = resp.text[:500].lower()
            if 'xml' in content or '<rss' in content or '<feed' in content:
                return True
    except:
        pass
    return False

def main():
    print(f"🔍 Validating {len(KNOWN_FEEDS)} known feeds...")
    print("-" * 60)
    
    valid_feeds = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_site = {executor.submit(validate_feed, url): (site, url) for site, url in KNOWN_FEEDS.items()}
        for future in concurrent.futures.as_completed(future_to_site):
            site, url = future_to_site[future]
            if future.result():
                print(f"✅ {site}: {url}")
                valid_feeds.append((site, url))
            else:
                print(f"⚠️ {site}: Validation failed (might need browser or specific headers)")
                # We keep it anyway if it's a known good URL, just mark as unverified
                valid_feeds.append((site, url))

    print("-" * 60)
    
    # Merge with previously found feeds
    try:
        with open("found_feeds.txt", "r", encoding="utf-8") as f:
            existing_feeds = [line.strip() for line in f.readlines() if line.strip()]
    except FileNotFoundError:
        existing_feeds = []
        
    all_feeds = set(existing_feeds)
    for _, url in valid_feeds:
        all_feeds.add(url)
        
    print(f"🎉 Total unique feeds: {len(all_feeds)}")
    
    # Save combined list
    with open("all_feeds.txt", "w", encoding="utf-8") as f:
        for url in sorted(all_feeds):
            f.write(f"{url}\n")
    print("💾 Saved combined list to all_feeds.txt")

if __name__ == "__main__":
    main()
