"""
Metadata extraction from HTML using JSON-LD, OpenGraph, Twitter Cards, and meta tags
"""

import json
import re
from typing import Dict, List, Optional, Any
from datetime import datetime
from bs4 import BeautifulSoup, Tag
import dateparser
import logging

logger = logging.getLogger(__name__)

def extract_jsonld(soup: BeautifulSoup) -> Dict[str, Any]:
    """Extract JSON-LD structured data"""
    jsonld_data = {}
    
    # Find all JSON-LD script tags
    scripts = soup.find_all('script', type='application/ld+json')
    
    for script in scripts:
        if not script.string:
            continue
            
        try:
            data = json.loads(script.string)
            
            # Handle array of JSON-LD objects
            if isinstance(data, list):
                for item in data:
                    try:
                        jsonld_data.update(_extract_jsonld_article_data(item) or {})
                    except (TypeError, AttributeError) as e:
                        logger.debug(f"Failed to extract from JSON-LD item: {e}")
                        continue
            else:
                try:
                    jsonld_data.update(_extract_jsonld_article_data(data) or {})
                except (TypeError, AttributeError) as e:
                    logger.debug(f"Failed to extract from JSON-LD data: {e}")
                    continue
                
        except (json.JSONDecodeError, TypeError) as e:
            logger.debug(f"Failed to parse JSON-LD: {e}")
            continue
    
    return jsonld_data

def _extract_jsonld_article_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """Extract article data from JSON-LD object"""
    if not isinstance(data, dict):
        return {}
    
    # Check if this is an article-type object
    type_field = data.get('@type', '').lower()
    if type_field not in ('article', 'newsarticle', 'blogposting', 'webpage'):
        return {}
    
    extracted = {}
    
    # Title
    if 'headline' in data:
        extracted['title'] = str(data['headline'])
    elif 'name' in data:
        extracted['title'] = str(data['name'])
    
    # Description
    if 'description' in data:
        extracted['description'] = str(data['description'])
    
    # Author
    authors = []
    if 'author' in data:
        author_data = data['author']
        if isinstance(author_data, list):
            for author in author_data:
                if isinstance(author, dict):
                    name = author.get('name', '')
                elif isinstance(author, str):
                    name = author
                else:
                    continue
                if name:
                    authors.append(name)
        elif isinstance(author_data, dict):
            name = author_data.get('name', '')
            if name:
                authors.append(name)
        elif isinstance(author_data, str):
            authors.append(author_data)
    
    if authors:
        extracted['authors'] = authors
    
    # Publisher
    if 'publisher' in data:
        pub_data = data['publisher']
        if isinstance(pub_data, dict):
            extracted['publisher'] = pub_data.get('name', '')
        elif isinstance(pub_data, str):
            extracted['publisher'] = pub_data
    
    # Dates
    for date_field, our_field in [
        ('datePublished', 'published_at'),
        ('dateModified', 'updated_at'),
        ('dateCreated', 'published_at')
    ]:
        if date_field in data:
            date_str = data[date_field]
            if date_str:
                parsed_date = _parse_date(date_str)
                if parsed_date:
                    extracted[our_field] = parsed_date
    
    # Keywords
    if 'keywords' in data:
        keywords_data = data['keywords']
        if isinstance(keywords_data, list):
            extracted['keywords'] = [str(k) for k in keywords_data if k]
        elif isinstance(keywords_data, str):
            # Split comma-separated keywords
            extracted['keywords'] = [k.strip() for k in keywords_data.split(',') if k.strip()]
    
    # Section/Category
    if 'section' in data:
        extracted['section'] = str(data['section'])
    elif 'articleSection' in data:
        extracted['section'] = str(data['articleSection'])
    
    # Image
    if 'image' in data:
        image_data = data['image']
        if isinstance(image_data, list) and image_data:
            image_data = image_data[0]
        
        if isinstance(image_data, dict):
            extracted['top_image'] = image_data.get('url', '')
        elif isinstance(image_data, str):
            extracted['top_image'] = image_data
    
    # Language
    if 'inLanguage' in data:
        extracted['language'] = str(data['inLanguage'])
    
    return extracted

def extract_opengraph(soup: BeautifulSoup) -> Dict[str, Any]:
    """Extract OpenGraph metadata"""
    og_data = {}
    
    # Find all OpenGraph meta tags
    og_tags = soup.find_all('meta', property=lambda x: x and x.startswith('og:'))
    
    for tag in og_tags:
        if not isinstance(tag, Tag):
            continue
            
        property_name = tag.get('property', '').replace('og:', '')
        content = tag.get('content', '').strip()
        
        if not content:
            continue
        
        if property_name == 'title':
            og_data['title'] = content
        elif property_name == 'description':
            og_data['description'] = content
        elif property_name == 'image':
            og_data['top_image'] = content
        elif property_name == 'url':
            og_data['canonical_url'] = content
        elif property_name == 'site_name':
            og_data['publisher'] = content
        elif property_name == 'locale':
            og_data['language'] = content.replace('_', '-').lower()
        elif property_name == 'type':
            og_data['og_type'] = content
    
    # Article-specific OG tags
    article_tags = soup.find_all('meta', property=lambda x: x and x.startswith('article:'))
    
    for tag in article_tags:
        property_name = tag.get('property', '').replace('article:', '')
        content = tag.get('content', '').strip()
        
        if not content:
            continue
        
        if property_name == 'published_time':
            parsed_date = _parse_date(content)
            if parsed_date:
                og_data['published_at'] = parsed_date
        elif property_name == 'modified_time':
            parsed_date = _parse_date(content)
            if parsed_date:
                og_data['updated_at'] = parsed_date
        elif property_name == 'author':
            if 'authors' not in og_data:
                og_data['authors'] = []
            og_data['authors'].append(content)
        elif property_name == 'section':
            og_data['section'] = content
        elif property_name == 'tag':
            if 'keywords' not in og_data:
                og_data['keywords'] = []
            og_data['keywords'].append(content)
    
    return og_data

def extract_twitter_cards(soup: BeautifulSoup) -> Dict[str, Any]:
    """Extract Twitter Card metadata"""
    twitter_data = {}
    
    # Find all Twitter meta tags
    twitter_tags = soup.find_all('meta', attrs={'name': lambda x: x and x.startswith('twitter:')})
    
    for tag in twitter_tags:
        if not isinstance(tag, Tag):
            continue
            
        name = tag.get('name', '').replace('twitter:', '')
        content = tag.get('content', '').strip()
        
        if not content:
            continue
        
        if name == 'title':
            twitter_data['title'] = content
        elif name == 'description':
            twitter_data['description'] = content
        elif name == 'image':
            twitter_data['top_image'] = content
        elif name == 'creator':
            if 'authors' not in twitter_data:
                twitter_data['authors'] = []
            # Remove @ prefix if present
            author = content.lstrip('@')
            twitter_data['authors'].append(author)
    
    return twitter_data

def extract_html_meta(soup: BeautifulSoup) -> Dict[str, Any]:
    """Extract standard HTML meta tags"""
    meta_data = {}
    
    # Standard meta tags
    meta_tags = {
        'description': 'description',
        'keywords': 'keywords',
        'author': 'authors',
        'news_keywords': 'keywords',
        'category': 'section',
        'section': 'section'
    }
    
    for meta_name, our_field in meta_tags.items():
        tag = soup.find('meta', attrs={'name': meta_name}) or soup.find('meta', attrs={'name': meta_name.replace('_', '-')})
        if tag:
            content = tag.get('content', '').strip()
            if content:
                if our_field == 'authors':
                    if 'authors' not in meta_data:
                        meta_data['authors'] = []
                    meta_data['authors'].append(content)
                elif our_field == 'keywords':
                    if 'keywords' not in meta_data:
                        meta_data['keywords'] = []
                    # Split comma-separated keywords
                    keywords = [k.strip() for k in content.split(',') if k.strip()]
                    meta_data['keywords'].extend(keywords)
                else:
                    meta_data[our_field] = content
    
    # Language from html tag
    html_tag = soup.find('html')
    if html_tag:
        lang = html_tag.get('lang')
        if lang:
            meta_data['language'] = lang.lower()
    
    # Canonical URL
    canonical_link = soup.find('link', rel='canonical')
    if canonical_link:
        href = canonical_link.get('href')
        if href:
            meta_data['canonical_url'] = href
    
    # Title from title tag (fallback)
    if 'title' not in meta_data:
        title_tag = soup.find('title')
        if title_tag and title_tag.string:
            meta_data['title'] = title_tag.string.strip()
    
    return meta_data

def extract_metadata(html: str, base_url: str = '') -> Dict[str, Any]:
    """
    Extract all metadata from HTML in priority order:
    1. JSON-LD
    2. OpenGraph
    3. Twitter Cards
    4. HTML meta tags
    """
    try:
        soup = BeautifulSoup(html, 'lxml')
    except Exception:
        try:
            soup = BeautifulSoup(html, 'html.parser')
        except Exception as e:
            logger.error(f"Failed to parse HTML: {e}")
            return {}
    
    # Extract from all sources with error handling
    try:
        jsonld_data = extract_jsonld(soup) or {}
    except Exception as e:
        logger.debug(f"JSON-LD extraction failed: {e}")
        jsonld_data = {}
        
    try:
        og_data = extract_opengraph(soup) or {}
    except Exception as e:
        logger.debug(f"OpenGraph extraction failed: {e}")
        og_data = {}
        
    try:
        twitter_data = extract_twitter_cards(soup) or {}
    except Exception as e:
        logger.debug(f"Twitter Cards extraction failed: {e}")
        twitter_data = {}
        
    try:
        meta_data = extract_html_meta(soup) or {}
    except Exception as e:
        logger.debug(f"HTML meta extraction failed: {e}")
        meta_data = {}
    
    # Merge in priority order (JSON-LD highest priority)
    merged = {}
    
    # Start with lowest priority
    for source_data in [meta_data, twitter_data, og_data, jsonld_data]:
        for key, value in source_data.items():
            if key not in merged or not merged[key]:
                merged[key] = value
            elif key in ('authors', 'keywords') and isinstance(value, list):
                # Merge lists, avoiding duplicates
                if isinstance(merged[key], list):
                    for item in value:
                        if item not in merged[key]:
                            merged[key].append(item)
                elif merged[key] and merged[key] not in value:
                    merged[key] = [merged[key]] + value
    
    # Clean and normalize data
    if 'keywords' in merged and isinstance(merged['keywords'], list):
        # Remove duplicates and empty values
        merged['keywords'] = list(set([k for k in merged['keywords'] if k and k.strip()]))
    
    if 'authors' in merged and isinstance(merged['authors'], list):
        # Remove duplicates
        merged['authors'] = list(set([a for a in merged['authors'] if a and a.strip()]))
    
    # Ensure dates are datetime objects
    for date_field in ['published_at', 'updated_at']:
        if date_field in merged and not isinstance(merged[date_field], datetime):
            parsed_date = _parse_date(merged[date_field])
            if parsed_date:
                merged[date_field] = parsed_date
            else:
                del merged[date_field]
    
    # Resolve relative URLs
    if base_url:
        for url_field in ['canonical_url', 'top_image']:
            if url_field in merged and merged[url_field]:
                from urllib.parse import urljoin
                merged[url_field] = urljoin(base_url, merged[url_field])
    
    return merged

def _parse_date(date_str: str) -> Optional[datetime]:
    """Parse date string to datetime object, normalized to UTC"""
    if not date_str or not isinstance(date_str, str):
        return None
    
    try:
        # Try dateparser first (handles many formats)
        parsed = dateparser.parse(date_str)
        if parsed:
            # Convert to UTC if timezone aware, otherwise assume UTC
            if parsed.tzinfo is not None:
                parsed = parsed.utctimetuple()
                parsed = datetime(*parsed[:6])
            return parsed
    except Exception as e:
        logger.debug(f"Failed to parse date '{date_str}': {e}")
    
    # Fallback to ISO format parsing
    try:
        # Handle common ISO formats
        for fmt in [
            '%Y-%m-%dT%H:%M:%SZ',
            '%Y-%m-%dT%H:%M:%S',
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d',
            '%d/%m/%Y',
            '%m/%d/%Y'
        ]:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
    except Exception:
        pass
    
    return None