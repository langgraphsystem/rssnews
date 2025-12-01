import requests
import logging

logging.basicConfig(level=logging.INFO, format='%(message)s')

feeds = [
    ("Yahoo News", "https://news.yahoo.com/rss"),
    ("NY Times", "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml"),
    ("CNN", "http://rss.cnn.com/rss/cnn_topstories.rss"),
    ("Fox News", "http://feeds.foxnews.com/foxnews/latest"),
    ("USA Today", "http://content.usatoday.com/marketing/rss/rsstrans.aspx?feedId=news2")
]

print("Validating RSS Feeds...")
print("-" * 60)

for name, url in feeds:
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200 and 'xml' in response.headers.get('Content-Type', '') or '<rss' in response.text[:200] or '<feed' in response.text[:200]:
            print(f"✅ {name}: Active")
            print(f"   URL: {url}")
        else:
            print(f"❌ {name}: Invalid (Status: {response.status_code})")
    except Exception as e:
        print(f"❌ {name}: Error ({e})")
print("-" * 60)
