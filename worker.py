import re
from typing import Dict, Tuple

import requests
from bs4 import BeautifulSoup
from langdetect import detect as langdetect_detect
import trafilatura

from config import (
    PENDING_BATCH_SIZE, CLEAN_TEXT_SHEETS_LIMIT, POLITICS_KEYS, SPORTS_KEYS, FULLTEXT_DIR
)
from sheets_client import SheetClient
from utils import (
    canonicalize_url, sha256_hex, normalize_text_for_hash, now_local_iso,
    json_dumps, store_fulltext, domain_of
)

def process_pending(client: SheetClient, worker_id: str = "worker-1"):
    ws = client.ws("Raw")
    header = ws.row_values(1)
    rows = ws.get_all_values()
    if len(rows)<2:
        return
    idx = {h:i for i,h in enumerate(header)}
    candidates = []
    now_iso = now_local_iso()

    for r, row in enumerate(rows[1:], start=2):
        status = (row[idx["status"]] if len(row)>idx["status"] else "").strip().lower()
        lock_owner = row[idx["lock_owner"]] if len(row)>idx["lock_owner"] else ""
        if status == "pending" and not lock_owner:
            candidates.append(r)
        if len(candidates) >= PENDING_BATCH_SIZE:
            break

    for r in candidates:
        ws.update_cell(r, idx["status"]+1, "processing")
        ws.update_cell(r, idx["lock_owner"]+1, worker_id)
        ws.update_cell(r, idx["lock_at"]+1, now_iso)

    for r in candidates:
        try:
            _process_row(client, ws, header, idx, r)
        except Exception as e:
            ws.update_cell(r, idx["status"]+1, "error")
            ws.update_cell(r, idx["error_msg"]+1, str(e)[:500])
        finally:
            status = ws.cell(r, idx["status"]+1).value or ""
            if status != "processing":
                ws.update_cell(r, idx["lock_owner"]+1, "")
                ws.update_cell(r, idx["lock_at"]+1, "")

def _process_row(client: SheetClient, ws, header, idx, r: int):
    article_url_canon = ws.cell(r, idx["article_url_canon"]+1).value or ""
    if not article_url_canon:
        article_url = ws.cell(r, idx["article_url"]+1).value or ""
        article_url_canon = canonicalize_url(article_url)
        ws.update_cell(r, idx["article_url_canon"]+1, article_url_canon)
    url_hash = sha256_hex(article_url_canon)
    ws.update_cell(r, idx["url_hash"]+1, url_hash)

    html, final_url = _fetch_html(article_url_canon)
    if final_url and final_url != article_url_canon:
        article_url_canon = canonicalize_url(final_url)
        url_hash = sha256_hex(article_url_canon)
        ws.update_cell(r, idx["article_url_canon"]+1, article_url_canon)
        ws.update_cell(r, idx["url_hash"]+1, url_hash)

    meta = extract_meta(html, article_url_canon)
    full_text, clean_text = extract_texts(html, article_url_canon)

    clean_for_hash = normalize_text_for_hash(clean_text)
    text_hash = sha256_hex(clean_for_hash)
    ws.update_cell(r, idx["text_hash"]+1, text_hash)

    category_guess = quick_category(meta["title"], clean_text)
    article_type = quick_article_type(meta, clean_text)

    full_text_ref = store_fulltext(url_hash, full_text, base_dir=FULLTEXT_DIR)

    clean_trim = clean_text[:CLEAN_TEXT_SHEETS_LIMIT]
    out_links_json = json_dumps(sorted(set(meta["out_links"]))) if meta["out_links"] else ""
    patch = {
        "fetched_at": now_local_iso(),
        "published_at": meta["published_at"] or ws.cell(r, idx["published_at"]+1).value or "",
        "language": meta["language"] or "",
        "title": meta["title"] or "",
        "subtitle": meta["subtitle"] or "",
        "authors": ", ".join(meta["authors"]) if meta["authors"] else "",
        "section": meta["section"] or "",
        "tags": ", ".join(meta["tags"]) if meta["tags"] else "",
        "article_type": article_type,
        "clean_text": clean_trim,
        "clean_text_len": str(len(clean_text)),
        "full_text_ref": full_text_ref,
        "full_text_len": str(len(full_text)),
        "word_count": str(len(clean_text.split())),
        "out_links": out_links_json,
        "category_guess": category_guess,
        "status": "stored",
        "processed_at": now_local_iso(),
    }
    client.update_raw_row(r, patch)

    index_entry = {
        "url_hash": url_hash,
        "text_hash": text_hash,
        "article_url_canon": article_url_canon,
        "row_id_raw": str(r),
        "first_seen": ws.cell(r, idx["found_at"]+1).value or now_local_iso(),
        "last_seen": now_local_iso(),
        "is_duplicate": "false",
        "reason": "",
        "language": meta["language"] or "",
        "category_guess": category_guess,
        "rev_n": "1",
    }
    client.upsert_index(index_entry)

def _fetch_html(url: str) -> Tuple[str,str]:
    headers = {"User-Agent": "NewsPipelineBot/1.0 (+https://example.com/bot)"}
    r = requests.get(url, timeout=25, headers=headers, allow_redirects=True)
    r.raise_for_status()
    return r.text, r.url

def extract_meta(html: str, base_url: str) -> Dict[str, any]:
    soup = BeautifulSoup(html, "lxml")
    def meta(name=None, prop=None):
        if name:
            tag = soup.find("meta", attrs={"name":name})
            if tag and tag.get("content"): return tag["content"].strip()
        if prop:
            tag = soup.find("meta", attrs={"property":prop})
            if tag and tag.get("content"): return tag["content"].strip()
        return ""

    title = meta(prop="og:title") or (soup.title.string.strip() if soup.title and soup.title.string else "")
    subtitle = meta(name="description") or meta(prop="og:description") or ""
    published = meta(prop="article:published_time") or ""
    if not published:
        time_tag = soup.find("time", attrs={"datetime":True})
        if time_tag: published = time_tag["datetime"].strip()
    authors = []
    a1 = meta(name="author")
    if a1: authors.append(a1)
    section = meta(prop="article:section") or ""
    tags = []
    kw = meta(name="keywords")
    if kw: tags.extend([t.strip() for t in kw.split(",") if t.strip()])
    for a in soup.select(".tags a, .article-tags a, a[rel='tag']"):
        if a.text and a.text.strip(): tags.append(a.text.strip())
    tags = list(dict.fromkeys(tags))
    html_tag = soup.find("html")
    language = (html_tag.get("lang","") if html_tag else "").lower()
    if not language and title:
        try: language = langdetect_detect(title)
        except Exception: language = ""
    out_links = set()
    base_dom = domain_of(base_url)
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith("#") or href.startswith("mailto:") or href.startswith("javascript:"): continue
        if href.startswith("/"):
            continue
        dom = domain_of(href)
        if dom and dom != base_dom: out_links.add(dom)

    return {
        "title": title,
        "subtitle": subtitle,
        "published_at": published,
        "authors": authors,
        "section": section,
        "tags": tags,
        "language": language if language.startswith("en") else language,
        "out_links": list(out_links),
    }

def extract_texts(html: str, url: str) -> Tuple[str,str]:
    downloaded = trafilatura.extract(html, include_comments=False, include_tables=True, no_fallback=False,
                                    favor_recall=True,  output="txt")
    full_text = downloaded or ""
    clean_text = _clean_text(full_text)
    return full_text, clean_text

REMOVALS = [
    r"^subscribe to.*$", r"^sign up.*$", r"^related articles.*$", r"^read more.*$",
    r"^©.*$", r"^copyright.*$", r"^all rights reserved.*$", r"^\s*$"
]
REMOVALS_RE = [re.compile(pat, re.IGNORECASE) for pat in REMOVALS]

def _clean_text(text: str) -> str:
    lines = [ln.strip() for ln in (text or "").splitlines()]
    kept = []
    for ln in lines:
        if any(rx.match(ln) for rx in REMOVALS_RE):
            continue
        kept.append(ln)
    out = "\n".join(kept)
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    return out

def quick_category(title: str, clean_text: str) -> str:
    txt = f"{title}\n{clean_text[:2000]}".lower()
    p_score = sum(1 for k in POLITICS_KEYS if k in txt)
    s_score = sum(1 for k in SPORTS_KEYS if k in txt)
    if p_score >= max(3, 2*s_score): return "politics"
    if s_score >= max(3, 2*p_score): return "sports"
    return "other"

def quick_article_type(meta: Dict[str,any], clean_text: str) -> str:
    label = " ".join([meta.get("section","") or "", ",".join(meta.get("tags",[]) or [])]).lower()
    head = (meta.get("title","") or "").lower()
    txt = f"{head}\n{clean_text[:2000]}".lower()
    if any(k in label or k in txt for k in ("opinion","editorial","op-ed","commentary","column")): return "opinion"
    if any(k in label or k in txt for k in ("analysis","explainer","what to know")): return "analysis"
    if "interview" in label or re.search(r"\bq:\b.*\ba:\b", txt): return "interview"
    if "live" in label or "live updates" in txt: return "live"
    return "news"
