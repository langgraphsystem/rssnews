import requests
from urllib.parse import urljoin
from bs4 import BeautifulSoup
import logging
import concurrent.futures
import time

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

SITES = [
    "yahoo.com", "nytimes.com", "cnn.com", "foxnews.com", "msn.com", "usatoday.com",
    "abcnews.go.com", "cbsnews.com", "nbcnews.com", "washingtonpost.com", "reuters.com",
    "apnews.com", "thehill.com", "axios.com", "bloomberg.com", "wsj.com",
    "latimes.com", "npr.org", "huffpost.com", "politico.com", "buzzfeed.com/news",
    "newsweek.com", "thedailybeast.com", "vice.com", "slate.com", "salon.com",
    "theatlantic.com", "wired.com", "theverge.com", "cnbc.com", "forbes.com",
    "time.com", "usnews.com", "propublica.org", "motherjones.com", "truthout.org",
    "theguardian.com/us-news", "cnet.com", "engadget.com", "arstechnica.com",
    "techcrunch.com", "scientificamerican.com", "nature.com", "rollingstone.com",
    "people.com", "variety.com", "hollywoodreporter.com", "espn.com", "deadspin.com",
    "theintercept.com", "nola.com", "chicagotribune.com", "nydailynews.com",
    "nypost.com", "dailynews.com", "newsday.com", "sfgate.com", "seattletimes.com",
    "baltimoresun.com", "startribune.com", "houstonchronicle.com", "miamiherald.com",
    "orlandosentinel.com", "denverpost.com", "sandiegouniontribune.com", "inquirer.com",
    "azcentral.com", "oregonlive.com", "al.com", "tulsaworld.com", "saltlaketribune.com",
    "dispatch.com", "cincinnati.com", "cleveland.com", "detroitnews.com", "freep.com",
    "observer.com", "dailycaller.com", "drudgereport.com", "zerohedge.com",
    "marketwatch.com", "barrons.com", "investopedia.com", "seekingalpha.com",
    "techradar.com", "tomshardware.com"
]

COMMON_PATHS = [
    "/rss", "/feed", "/rss.xml", "/feed.xml", "/index.xml", 
    "/feeds/news.xml", "/rss/index.xml", "/services/xml/rss/nyt/HomePage.xml",
    "/rss/cnn_topstories.rss", "/foxnews/latest", "/arc/outboundfeeds/rss/"
]

def find_feed(site):
    base_url = f"https://{site}" if not site.startswith("http") else site
    
    # 1. Try common paths
    for path in COMMON_PATHS:
        url = urljoin(base_url, path)
        try:
            resp = requests.get(url, timeout=3)
            if resp.status_code == 200 and ('xml' in resp.headers.get('Content-Type', '') or '<rss' in resp.text[:200] or '<feed' in resp.text[:200]):
                return site, url
        except:
            continue
            
    # 2. Try parsing homepage for <link rel="alternate" type="application/rss+xml">
    try:
        resp = requests.get(base_url, timeout=5)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            link = soup.find('link', type='application/rss+xml')
            if link and link.get('href'):
                feed_url = urljoin(base_url, link.get('href'))
                return site, feed_url
    except:
        pass
        
    return site, None

def main():
    print(f"🔍 Scanning {len(SITES)} sites for RSS feeds...")
    print("-" * 60)
    
    found_feeds = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_site = {executor.submit(find_feed, site): site for site in SITES}
        for future in concurrent.futures.as_completed(future_to_site):
            site = future_to_site[future]
            try:
                site_name, feed_url = future.result()
                if feed_url:
                    print(f"✅ {site_name}: {feed_url}")
                    found_feeds.append((site_name, feed_url))
                else:
                    print(f"❌ {site_name}: Not found")
            except Exception as e:
                print(f"❌ {site}: Error ({e})")
                
    print("-" * 60)
    print(f"🎉 Found {len(found_feeds)} feeds out of {len(SITES)}")
    
    # Save to file
    with open("found_feeds.txt", "w", encoding="utf-8") as f:
        for site, url in found_feeds:
            f.write(f"{url}\n")
    print("💾 Saved list to found_feeds.txt")

if __name__ == "__main__":
    main()
