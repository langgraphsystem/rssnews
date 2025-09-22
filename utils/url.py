"""
URL normalization and canonicalization utilities
"""

import re
import hashlib
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode, parse_qsl
from typing import Optional
import tldextract

# NOTE: keep this canon exactly the same anywhere url_hash is used.
# If you already have canonicalize_url() here, reuse it and delete this copy.

# Common tracking parameters to remove
TRACKING_PARAMS = {
    'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
    'utm_name', 'utm_cid', 'utm_reader', 'utm_viz_id', 'utm_pubreferrer',
    'fbclid', 'gclid', 'msclkid', 'mc_cid', 'mc_eid', '_hsenc', '_hsmi',
    'icid', 'ref', 'referer', 'referrer', 'campaign_id', 'ad_id',
    'campaign', 'source', 'medium', 'content', 'term'
}

def remove_tracking_params(url: str) -> str:
    """Remove common tracking parameters from URL"""
    parsed = urlparse(url)
    if not parsed.query:
        return url
        
    query_params = parse_qs(parsed.query, keep_blank_values=True)
    
    # Remove tracking parameters
    cleaned_params = {
        k: v for k, v in query_params.items() 
        if k.lower() not in TRACKING_PARAMS
    }
    
    # Rebuild URL
    new_query = urlencode(cleaned_params, doseq=True) if cleaned_params else ''
    cleaned = parsed._replace(query=new_query)
    
    return urlunparse(cleaned)

def normalize_url(url: str) -> str:
    """
    Normalize URL by:
    - Converting to lowercase (except path/query)
    - Removing tracking parameters
    - Ensuring https scheme when possible
    - Removing trailing slashes
    - Removing fragments
    """
    if not url or not isinstance(url, str):
        return ''
        
    url = url.strip()
    if not url:
        return ''
    
    # Add scheme if missing
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    parsed = urlparse(url)
    
    # Normalize scheme - prefer https
    scheme = parsed.scheme.lower()
    if scheme == 'http':
        scheme = 'https'
    elif scheme not in ('http', 'https'):
        return ''  # Invalid scheme
    
    # Normalize netloc - lowercase domain
    netloc = parsed.netloc.lower() if parsed.netloc else ''
    
    # Keep path as-is (case sensitive)
    path = parsed.path
    
    # Remove trailing slash from path (except for root)
    if path and path != '/' and path.endswith('/'):
        path = path.rstrip('/')
    
    # Clean query parameters
    if parsed.query:
        query_params = parse_qs(parsed.query, keep_blank_values=True)
        # Remove tracking parameters
        cleaned_params = {
            k: v for k, v in query_params.items() 
            if k.lower() not in TRACKING_PARAMS
        }
        query = urlencode(cleaned_params, doseq=True) if cleaned_params else ''
    else:
        query = ''
    
    # Remove fragments
    fragment = ''
    
    normalized = urlunparse((scheme, netloc, path, parsed.params, query, fragment))
    return normalized

def canonicalize_url(url: str) -> str:
    """
    Canonical form:
      - lowercase scheme/host
      - strip default ports
      - sort + drop tracking query params
      - normalize path (remove trailing slash except root)
    """
    # Be robust to non-string inputs (e.g., lists from metadata)
    if isinstance(url, (list, tuple)):
        url = url[0] if url else ""
    if url is None:
        url = ""
    url = str(url)
    u = urlparse(url.strip())
    scheme = (u.scheme or "http").lower()
    netloc = u.hostname.lower() if u.hostname else ""
    if u.port and not ((scheme == "http" and u.port == 80) or (scheme == "https" and u.port == 443)):
        netloc = f"{netloc}:{u.port}"
    # Drop tracking parameters using global TRACKING_PARAMS (case-insensitive)
    qs = [(k, v) for k, v in parse_qsl(u.query, keep_blank_values=True) if k.lower() not in TRACKING_PARAMS]
    qs_sorted = urlencode(sorted(qs))
    path = u.path or "/"
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    canon = urlunparse((scheme, netloc, path, "", qs_sorted, ""))
    return canon

def compute_url_hash(url: str) -> str:
    canon = canonicalize_url(url)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()

def extract_domain(url: str) -> str:
    """Extract domain from URL"""
    if not url:
        return ''
    
    try:
        extracted = tldextract.extract(url)
        if extracted.domain and extracted.suffix:
            return f"{extracted.domain}.{extracted.suffix}"
        return ''
    except Exception:
        # Fallback to basic parsing
        try:
            parsed = urlparse(url)
            if parsed.netloc:
                # Remove www. prefix if present
                domain = parsed.netloc.lower()
                if domain.startswith('www.'):
                    domain = domain[4:]
                return domain
            return ''
        except Exception:
            return ''

def is_valid_url(url: str) -> bool:
    """Check if URL is valid"""
    if not url or not isinstance(url, str):
        return False
        
    try:
        parsed = urlparse(url)
        return all([
            parsed.scheme in ('http', 'https'),
            parsed.netloc,
            '.' in parsed.netloc  # Has domain extension
        ])
    except Exception:
        return False

def resolve_relative_url(base_url: str, relative_url: str) -> str:
    """Resolve relative URL against base URL"""
    if not relative_url:
        return base_url
        
    if is_valid_url(relative_url):
        return relative_url
        
    try:
        from urllib.parse import urljoin
        return urljoin(base_url, relative_url)
    except Exception:
        return base_url
