"""
Utility modules for RSS news aggregation pipeline
"""

from datetime import datetime
import json
import hashlib
import os
from typing import Optional
import pytz

from .url import normalize_url, canonicalize_url, extract_domain, remove_tracking_params
from .text import compute_text_hash, compute_word_count, estimate_reading_time, normalize_text

__all__ = [
    'normalize_url',
    'canonicalize_url', 
    'extract_domain',
    'remove_tracking_params',
    'compute_text_hash',
    'compute_word_count', 
    'estimate_reading_time',
    'normalize_text',
    # Legacy functions for backward compatibility
    'now_local_iso',
    'json_dumps',
    'sha256_hex',
    'normalize_text_for_hash',
    'domain_of',
    'store_fulltext',
    'parse_dt',
    'iso_or_empty'
]

# Legacy functions for backward compatibility with old code
def now_local_iso():
    """Return current datetime as ISO string"""
    return datetime.now().isoformat()

def json_dumps(obj):
    """JSON serialize with proper formatting"""
    return json.dumps(obj, indent=2, ensure_ascii=False)

def sha256_hex(text):
    """Return SHA256 hash of text"""
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

def normalize_text_for_hash(text):
    """Normalize text for hashing - legacy wrapper"""
    return normalize_text(text)

def domain_of(url):
    """Extract domain from URL - legacy wrapper"""
    return extract_domain(url)

def store_fulltext(url_hash, full_text, base_dir="storage"):
    """Store full text to file"""
    os.makedirs(base_dir, exist_ok=True)
    filename = f"{base_dir}/{url_hash}.txt"
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(full_text)
    return filename

def parse_dt(date_str) -> Optional[datetime]:
    """Parse date string to datetime"""
    if not date_str:
        return None
    try:
        from dateutil.parser import parse
        return parse(date_str)
    except:
        return None

def iso_or_empty(dt) -> str:
    """Convert datetime to ISO string or empty string"""
    if dt and hasattr(dt, 'isoformat'):
        return dt.isoformat()
    return ""