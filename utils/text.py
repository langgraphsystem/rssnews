"""
Text processing and hashing utilities
"""

import hashlib
import re
from typing import List, Optional

def normalize_text(text: str) -> str:
    """
    Normalize text for consistent hashing:
    - Strip whitespace
    - Normalize whitespace (multiple spaces -> single space)
    - Remove excessive newlines
    """
    if not text:
        return ''
    
    # Strip leading/trailing whitespace
    text = text.strip()
    
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text)
    
    # Remove excessive newlines (3+ consecutive newlines -> 2)
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text

def compute_text_hash(text: str) -> str:
    """Compute SHA-256 hash of normalized text"""
    normalized = normalize_text(text)
    if not normalized:
        return ''
    
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()

def compute_word_count(text: str) -> int:
    """Compute word count from text"""
    if not text:
        return 0
    
    # Simple word counting - split on whitespace
    words = text.split()
    return len(words)

def estimate_reading_time(text: str, wpm: int = 200) -> int:
    """
    Estimate reading time in minutes
    Default: 200 words per minute
    """
    word_count = compute_word_count(text)
    if word_count == 0:
        return 0
    
    # Round up to at least 1 minute
    return max(1, round(word_count / wpm))

def extract_keywords(text: str, max_keywords: int = 10) -> List[str]:
    """
    Extract potential keywords from text
    Simple approach: find common meaningful words
    """
    if not text:
        return []
    
    # Convert to lowercase and extract words
    words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
    
    # Filter out common stop words
    stop_words = {
        'the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can', 'had',
        'her', 'was', 'one', 'our', 'out', 'day', 'get', 'has', 'him', 'his',
        'how', 'man', 'new', 'now', 'old', 'see', 'two', 'way', 'who', 'boy',
        'did', 'its', 'let', 'put', 'say', 'she', 'too', 'use', 'will', 'with',
        'that', 'this', 'have', 'from', 'they', 'know', 'want', 'been', 'good',
        'much', 'some', 'time', 'very', 'when', 'come', 'here', 'just', 'like',
        'long', 'make', 'many', 'over', 'such', 'take', 'than', 'them', 'well',
        'were', 'what'
    }
    
    # Count word frequencies
    word_freq = {}
    for word in words:
        if word not in stop_words and len(word) > 3:
            word_freq[word] = word_freq.get(word, 0) + 1
    
    # Sort by frequency and return top keywords
    sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
    return [word for word, freq in sorted_words[:max_keywords]]

def clean_text_content(text: str) -> str:
    """
    Clean extracted text content:
    - Remove excessive whitespace
    - Remove social media handles/hashtags
    - Remove URLs
    - Clean up common artifacts
    """
    if not text:
        return ''
    
    # Remove URLs
    text = re.sub(r'https?://\S+|www\.\S+', '', text)
    
    # Remove social media handles and hashtags
    text = re.sub(r'@\w+|#\w+', '', text)
    
    # Remove email addresses
    text = re.sub(r'\S+@\S+', '', text)
    
    # Clean up common artifacts
    text = re.sub(r'\[.*?\]|\(.*?\)', '', text)  # Remove bracketed content
    text = re.sub(r'\s*[-–—]\s*', ' - ', text)   # Normalize dashes
    
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'\n\s*\n', '\n\n', text)  # Normalize paragraph breaks
    
    return text.strip()

def is_sufficient_content(text: str, min_length: int = 200) -> bool:
    """
    Check if text content is sufficient for a valid article
    """
    if not text:
        return False
    
    clean_text = clean_text_content(text)
    word_count = compute_word_count(clean_text)
    
    return word_count >= min_length

def detect_paywall_indicators(text: str, html: str = '') -> dict:
    """
    Detect potential paywall or partial content indicators
    Returns dict with flags and confidence
    """
    indicators = {
        'paywalled': False,
        'partial': False,
        'confidence': 0.0,
        'signals': []
    }
    
    if not text:
        return indicators
    
    # Check for common paywall phrases
    paywall_phrases = [
        'subscribe', 'subscription', 'paywall', 'premium content',
        'sign up', 'register', 'login required', 'member only',
        'full article', 'read more', 'continue reading',
        'upgrade to premium', 'unlock', 'paid content'
    ]
    
    text_lower = text.lower()
    signals = []
    
    for phrase in paywall_phrases:
        if phrase in text_lower:
            signals.append(f"paywall_phrase_{phrase.replace(' ', '_')}")
    
    # Check HTML for paywall indicators if provided
    if html:
        html_lower = html.lower()
        paywall_classes = ['paywall', 'subscription', 'premium', 'locked']
        
        for cls in paywall_classes:
            if f'class="{cls}"' in html_lower or f"class='{cls}'" in html_lower:
                signals.append(f"paywall_class_{cls}")
    
    # Check content length (very short might indicate paywall)
    word_count = compute_word_count(text)
    if word_count < 50:
        signals.append('very_short_content')
        indicators['partial'] = True
    elif word_count < 100:
        signals.append('short_content')
    
    # Determine flags based on signals
    if any('paywall' in s for s in signals):
        indicators['paywalled'] = True
        indicators['confidence'] = min(1.0, len(signals) * 0.3)
    elif signals:
        indicators['partial'] = True
        indicators['confidence'] = min(1.0, len(signals) * 0.2)
    
    indicators['signals'] = signals
    return indicators