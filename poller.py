import time
import feedparser
import requests
from dateutil import parser as dtparser

from config import MAX_ITEMS_PER_FEED_PER_POLL
from pg_client import PgClient
from utils import (
    canonicalize_url,
    sha256_hex,
    iso_or_empty,
    parse_dt,
    now_local_iso,
)


def poll_active_feeds(client: PgClient):
    active_feeds = client.get_active_feeds()
    if not active_feeds:
        return
    
    for feed in active_feeds:
        if feed.get("status") != "active":
            continue
        feed_url_canon = feed["feed_url_canon"]
        etag = feed.get("etag", "")
        last_mod = feed.get("last_modified", "")
        headers = {}
        if etag:
            headers["If-None-Match"] = etag
        if last_mod:
            headers["If-Modified-Since"] = last_mod
        try:
            resp = requests.get(feed_url_canon, headers=headers, timeout=25)
        except Exception:
            continue
        if resp.status_code == 304:
            patches = {
                "last_crawled": now_local_iso(),
                "checked_at": now_local_iso(),
            }
            client.update_feed(feed["id"], patches)
            continue
        if resp.status_code != 200:
            patches = {
                "last_crawled": now_local_iso(),
                "health_score": "80",
                "checked_at": now_local_iso(),
            }
            client.update_feed(feed["id"], patches)
            continue
        fp = feedparser.parse(resp.content)
        last_dt = _max_entry_dt(fp)
        patches = {
            "last_crawled": now_local_iso(),
            "etag": resp.headers.get("ETag", ""),
            "last_modified": resp.headers.get("Last-Modified", ""),
            "last_entry_date": (
                iso_or_empty(last_dt)
                if last_dt
                else feed.get("last_entry_date", "")
            ),
            "checked_at": now_local_iso(),
        }
        client.update_feed(feed["id"], patches)

        count = 0
        for e in fp.entries:
            if count >= MAX_ITEMS_PER_FEED_PER_POLL:
                break
            link = _best_link(e)
            if not link:
                continue
            article_url_canon = canonicalize_url(link)
            url_hash = sha256_hex(article_url_canon)
            existing_row_id = client.find_row_by_url_hash(url_hash)
            rss_title = getattr(e, "title", "") or ""
            rss_summary = getattr(e, "summary", "") or ""
            rss_categories = (
                ",".join(
                    [t.term for t in getattr(e, "tags", []) if getattr(t, "term", None)]
                )
                if getattr(e, "tags", None)
                else ""
            )
            published_at = None
            for k in ("published", "updated", "created"):
                if hasattr(e, k):
                    published_at = parse_dt(getattr(e, k))
                    break
            if existing_row_id:
                client.update_raw_row(
                    existing_row_id,
                    {
                        "last_seen_rss": now_local_iso(),
                    },
                )
                continue
            data = {
                "source": "",
                "feed_url": feed.get("feed_url", feed_url_canon),
                "article_url": link,
                "article_url_canon": article_url_canon,
                "url_hash": url_hash,
                "text_hash": "",
                "found_at": now_local_iso(),
                "fetched_at": "",
                "published_at": iso_or_empty(published_at),
                "language": "",
                "title": "",
                "subtitle": "",
                "authors": "",
                "section": "",
                "tags": "",
                "article_type": "",
                "clean_text": "",
                "clean_text_len": 0,
                "full_text_ref": "",
                "full_text_len": 0,
                "word_count": 0,
                "out_links": "",
                "category_guess": "",
                "status": "pending",
                "lock_owner": "",
                "lock_at": "",
                "processed_at": "",
                "retries": 0,
                "error_msg": "",
                "sources_list": f'["{feed.get("feed_url", feed_url_canon)}"]',
                "aliases": "[]",
                "last_seen_rss": now_local_iso(),
            }
            try:
                client.append_raw_minimal(data)
                count += 1
            except Exception as e:
                if "duplicate key" in str(e) and "url_hash" in str(e):
                    # Статья уже существует - это нормально, пропускаем тихо
                    continue
                else:
                    # Другая ошибка - пробрасываем дальше
                    raise
        time.sleep(0.25)



def _max_entry_dt(fp):
    best = None
    for e in fp.entries[:20]:
        for k in ("published", "updated", "created"):
            if hasattr(e, k):
                dt = dtparser.parse(getattr(e, k))
                if best is None or (dt and dt > best):
                    best = dt
                break
    return best


def _best_link(e):
    if getattr(e, "link", None):
        return e.link
    if getattr(e, "id", None) and str(e.id).startswith("http"):
        return e.id
    if getattr(e, "links", None):
        for L in e.links:
            if L.get("rel") in (None, "alternate") and L.get("href", "").startswith(
                "http"
            ):
                return L["href"]
    return None
