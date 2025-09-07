import requests
import feedparser
from datetime import datetime
from typing import Optional

from config import FRESH_DAYS_LIMIT, TZ
from pg_client_new import PgClient
from utils import canonicalize_url, parse_dt, iso_or_empty, now_local_iso
import pytz


def _last_entry_date(fp) -> Optional[datetime]:
    dates = []
    for e in fp.entries[:20]:
        for k in ("published", "updated", "created"):
            if hasattr(e, k):
                dt = parse_dt(getattr(e, k))
                if dt:
                    dates.append(dt)
                    break
    return max(dates) if dates else None


def ensure_feed(client: PgClient, feed_url: str):
    url_canon = canonicalize_url(feed_url)
    try:
        r = requests.get(url_canon, timeout=20)
        r.raise_for_status()
    except Exception:
        return
    fp = feedparser.parse(r.content)
    last_dt = _last_entry_date(fp)
    if not last_dt:
        return
    tz = pytz.timezone(TZ)
    now_local = datetime.now(tz)
    no_updates_days = (now_local - last_dt).days
    if no_updates_days >= FRESH_DAYS_LIMIT:
        return
    lang = (getattr(fp.feed, "language", "") or "en").lower()
    if not lang.startswith("en"):
        return
    row = {
        "feed_url": feed_url,
        "feed_url_canon": url_canon,
        "lang": lang,
        "status": "active",
        "last_entry_date": iso_or_empty(last_dt),
        "last_crawled": "",
        "no_updates_days": str(no_updates_days),
        "etag": r.headers.get("ETag", ""),
        "last_modified": r.headers.get("Last-Modified", ""),
        "health_score": "100",
        "notes": "",
        "checked_at": now_local_iso(),
    }
    client.upsert_feed(row)
