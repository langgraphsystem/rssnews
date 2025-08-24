import time
from datetime import datetime
import feedparser
import requests
from dateutil import parser as dtparser

from config import MAX_ITEMS_PER_FEED_PER_POLL
from sheets_client import SheetClient
from utils import canonicalize_url, sha256_hex, iso_or_empty, parse_dt, now_local_iso, domain_of

def poll_active_feeds(client: SheetClient):
    feeds_ws = client.ws("Feeds")
    rows = feeds_ws.get_all_values()
    if len(rows)<2:
        return
    header = rows[0]
    idx = {h:i for i,h in enumerate(header)}
    for r, row in enumerate(rows[1:], start=2):
        status = row[idx["status"]] if "status" in idx and len(row)>idx["status"] else ""
        if status != "active":
            continue
        feed_url_canon = row[idx["feed_url_canon"]]
        etag = row[idx["etag"]] if len(row)>idx["etag"] else ""
        last_mod = row[idx["last_modified"]] if len(row)>idx["last_modified"] else ""
        headers = {}
        if etag: headers["If-None-Match"] = etag
        if last_mod: headers["If-Modified-Since"] = last_mod
        try:
            resp = requests.get(feed_url_canon, headers=headers, timeout=25)
        except Exception:
            continue
        if resp.status_code == 304:
            patches = {
                "last_crawled": now_local_iso(),
                "checked_at": now_local_iso(),
            }
            _update_feed_row(feeds_ws, r, header, patches)
            continue
        if resp.status_code != 200:
            patches = {
                "last_crawled": now_local_iso(),
                "health_score": "80",
                "checked_at": now_local_iso(),
            }
            _update_feed_row(feeds_ws, r, header, patches)
            continue
        fp = feedparser.parse(resp.content)
        last_dt = _max_entry_dt(fp)
        patches = {
            "last_crawled": now_local_iso(),
            "etag": resp.headers.get("ETag",""),
            "last_modified": resp.headers.get("Last-Modified",""),
            "last_entry_date": iso_or_empty(last_dt) if last_dt else (row[idx["last_entry_date"]] if "last_entry_date" in idx else ""),
            "checked_at": now_local_iso(),
        }
        _update_feed_row(feeds_ws, r, header, patches)

        count = 0
        for e in fp.entries:
            if count >= MAX_ITEMS_PER_FEED_PER_POLL: break
            link = _best_link(e)
            if not link: continue
            article_url_canon = canonicalize_url(link)
            url_hash = sha256_hex(article_url_canon)
            existing_row_id = client.find_row_by_url_hash(url_hash)
            rss_title = getattr(e,"title","") or ""
            rss_summary = getattr(e,"summary","") or ""
            rss_categories = ",".join([t.term for t in getattr(e,"tags",[]) if getattr(t,"term",None)]) if getattr(e,"tags",None) else ""
            published_at = None
            for k in ("published","updated","created"):
                if hasattr(e,k):
                    published_at = parse_dt(getattr(e,k)); break
            if existing_row_id:
                client.update_raw_row(existing_row_id, {
                    "rss_title": rss_title,
                    "rss_summary": rss_summary,
                    "rss_categories": rss_categories,
                    "last_seen_rss": now_local_iso(),
                })
                continue
            data = {
                "source": "",
                "feed_url": row[idx["feed_url"]] if "feed_url" in idx else feed_url_canon,
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
                "clean_text_len": "",
                "full_text_ref": "",
                "full_text_len": "",
                "word_count": "",
                "out_links": "",
                "category_guess": "",
                "status": "pending",
                "lock_owner": "",
                "lock_at": "",
                "processed_at": "",
                "retries": "0",
                "error_msg": "",
                "sources_list": f'["{row[idx["feed_url"]] if "feed_url" in idx else feed_url_canon}"]',
                "aliases": "[]",
                "last_seen_rss": now_local_iso(),
                "rss_title": rss_title,
                "rss_summary": rss_summary,
                "rss_categories": rss_categories,
            }
            client.append_raw_minimal(data)
            count += 1
        time.sleep(0.25)

def _update_feed_row(ws, rownum, header, patches):
    for k,v in patches.items():
        if k in header:
            col = header.index(k)+1
            ws.update_cell(rownum, col, v)

def _max_entry_dt(fp):
    best = None
    for e in fp.entries[:20]:
        for k in ("published","updated","created"):
            if hasattr(e,k):
                dt = dtparser.parse(getattr(e,k))
                if best is None or (dt and dt > best):
                    best = dt
                break
    return best

def _best_link(e):
    if getattr(e,"link",None): return e.link
    if getattr(e,"id",None) and str(e.id).startswith("http"): return e.id
    if getattr(e,"links",None):
        for L in e.links:
            if L.get("rel") in (None,"alternate") and L.get("href","").startswith("http"):
                return L["href"]
    return None
