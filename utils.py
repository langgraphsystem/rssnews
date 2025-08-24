import hashlib
import json
import os
import re
from datetime import datetime, timezone
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

import pytz
import tldextract
from dateutil import parser as dtparser

from config import TRACKING_PARAMS, REMOVE_PATH_SUFFIXES, TZ

TZ_OBJ = pytz.timezone(TZ)

def now_local_iso():
    return datetime.now(TZ_OBJ).isoformat(timespec="seconds")

def parse_dt(value):
    if not value:
        return None
    try:
        dt = dtparser.parse(value)
        if not dt.tzinfo:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(TZ_OBJ)
    except Exception:
        return None

def iso_or_empty(dt):
    return dt.isoformat(timespec="seconds") if dt else ""

def canonicalize_url(url: str) -> str:
    if not url:
        return url
    u = urlparse(url.strip())
    scheme = "https" if u.scheme in ("http","https") else "https"
    netloc = u.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = u.path or "/"
    for suf in sorted(REMOVE_PATH_SUFFIXES, key=len, reverse=True):
        if path.endswith(suf):
            path = path[: -len(suf)] or "/"
    fragment = ""
    q = [(k,v) for k,v in parse_qsl(u.query, keep_blank_values=False) if k.lower() not in TRACKING_PARAMS]
    q = [(k,v) for k,v in q if k.lower() != "amp"]
    query = urlencode(q, doseq=True)
    return urlunparse((scheme, netloc, path, "", query, fragment))

def sha256_hex(s: str) -> str:
    if s is None:
        s = ""
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

MULTISPACE_RE = re.compile(r"\s+")
def normalize_text_for_hash(text: str) -> str:
    if not text:
        return ""
    t = text.replace("\u00a0", " ")
    t = MULTISPACE_RE.sub(" ", t).strip().lower()
    return t

def domain_of(url: str) -> str:
    try:
        ex = tldextract.extract(url)
        if not ex.domain:
            return ""
        return ".".join(part for part in [ex.domain, ex.suffix] if part)
    except Exception:
        return ""

def json_dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",",":"))

def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)

def store_fulltext(url_hash: str, text: str, base_dir: str) -> str:
    today = datetime.now(TZ_OBJ)
    rel = f"{today:%Y/%m/%d}/{url_hash}.txt"
    path = os.path.join(base_dir, rel)
    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        f.write(text or "")
    return path
