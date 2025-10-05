# Fox News and Fox Business RSS Feeds

**Date Added:** 2025-10-05
**Total Feeds:** 19
**Status:** ✅ All feeds successfully added to database

---

## Fox News Feeds (11 feeds)

| Category | RSS Feed URL |
|----------|--------------|
| Latest Headlines (All) | https://moxie.foxnews.com/google-publisher/latest.xml |
| World | https://moxie.foxnews.com/google-publisher/world.xml |
| Politics | https://moxie.foxnews.com/google-publisher/politics.xml |
| Science | https://moxie.foxnews.com/google-publisher/science.xml |
| Health | https://moxie.foxnews.com/google-publisher/health.xml |
| Sports | https://moxie.foxnews.com/google-publisher/sports.xml |
| Travel | https://moxie.foxnews.com/google-publisher/travel.xml |
| Technology | https://moxie.foxnews.com/google-publisher/tech.xml |
| Opinion | https://moxie.foxnews.com/google-publisher/opinion.xml |
| U.S. News | https://moxie.foxnews.com/google-publisher/us.xml |
| Videos | https://moxie.foxnews.com/google-publisher/videos.xml |

---

## Fox Business Feeds (8 feeds)

| Category | RSS Feed URL |
|----------|--------------|
| Latest Business News | https://moxie.foxbusiness.com/google-publisher/latest.xml |
| Economy | https://moxie.foxbusiness.com/google-publisher/economy.xml |
| Markets | https://moxie.foxbusiness.com/google-publisher/markets.xml |
| Personal Finance | https://moxie.foxbusiness.com/google-publisher/personal-finance.xml |
| Lifestyle | https://moxie.foxbusiness.com/google-publisher/lifestyle.xml |
| Real Estate | https://moxie.foxbusiness.com/google-publisher/real-estate.xml |
| Technology | https://moxie.foxbusiness.com/google-publisher/technology.xml |
| Videos | https://moxie.foxbusiness.com/google-publisher/videos.xml |

---

## Database Statistics

```
📊 Current Status:
  ✅ Fox News feeds:      11
  ✅ Fox Business feeds:   8
  ✅ Total Fox feeds:     19
  📈 Total feeds in DB:  137
```

---

## Feed Configuration Details

All feeds added with:
- **Language:** `en` (English)
- **Status:** `active`
- **Categories:** Matched to content type (news, world, politics, business, etc.)

---

## Usage

### Manually trigger RSS poll for Fox feeds:

```bash
# Poll all feeds (including Fox)
railway run python main.py poll --workers 10 --batch-size 10

# Or use the cron service (d116f94c)
# It will automatically poll all active feeds including Fox
```

### Check Fox feed statistics:

```bash
railway run python -c "
from pg_client_new import PgClient
db = PgClient()
with db._cursor() as cur:
    cur.execute('''
        SELECT
            COUNT(DISTINCT f.id) as feed_count,
            COUNT(r.id) as article_count
        FROM feeds f
        LEFT JOIN raw r ON r.feed_id = f.id
        WHERE f.feed_url LIKE '%fox%'
    ''')
    feeds, articles = cur.fetchone()
    print(f'Fox Feeds: {feeds}')
    print(f'Fox Articles: {articles:,}')
"
```

### Monitor Fox article processing:

```bash
railway run python -c "
from pg_client_new import PgClient
db = PgClient()
with db._cursor() as cur:
    cur.execute('''
        SELECT
            r.status,
            COUNT(*) as count
        FROM raw r
        JOIN feeds f ON r.feed_id = f.id
        WHERE f.feed_url LIKE '%fox%'
        GROUP BY r.status
        ORDER BY count DESC
    ''')
    for status, count in cur.fetchall():
        print(f'{status:15} {count:,}')
"
```

---

## Pipeline Processing

Once articles are polled from Fox feeds, they flow through the automated pipeline:

```
RSS POLL (d116f94c) - Cron scheduled
    ↓
Articles → raw table (status='pending')
    ↓
WORK Service (4692233a) - Continuous 30s
    ↓
Fulltext extraction → fulltext table
    ├─────────────────────┬────────────────────┐
    ↓                     ↓                    ↓
CHUNK (f32c1205)     FTS (ffe65f79)      (parallel)
30s interval          60s interval
    ↓                     ↓
article_chunks        fts_vector indexes
    ↓
OpenAI Embeddings (c015bdb5) - 60s interval
    ↓
embedding_vector (3072-dim)
    ↓
✅ Ready for Hybrid Search (Telegram bot)
```

---

## Next Steps

1. ✅ **Feeds Added** - All 19 Fox feeds in database
2. ⏳ **Wait for Poll** - RSS POLL service will fetch articles on next cron run
3. ⏳ **Automatic Processing** - WORK → CHUNK → FTS → Embeddings (fully automated)
4. ✅ **Search Ready** - Articles searchable via Telegram bot after processing

---

## Related Files

- [add_fox_feeds.py](add_fox_feeds.py) - Script used to add feeds
- [RAILWAY_SERVICES_CONFIG.md](RAILWAY_SERVICES_CONFIG.md) - Complete service configuration
- [pg_client_new.py](pg_client_new.py) - Database client with `insert_feed()` method

---

## Notes

- Fox News and Fox Business use Google Publisher format RSS feeds
- All feeds are hosted on `moxie.foxnews.com` and `moxie.foxbusiness.com`
- Feeds are optimized for news aggregators with full article metadata
- Videos feeds include video content metadata
- All feeds update frequently (typically every 15-30 minutes)

**Total RSS feeds in system: 137** (as of 2025-10-05)
