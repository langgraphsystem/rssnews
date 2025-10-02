"""
PII Masker — Automatically detects and masks personally identifiable information.
Extends PolicyValidator with auto-masking and domain trust scoring.
"""

import re
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class PIIMasker:
    """Detects and masks PII in text"""

    # Extended PII patterns
    PII_PATTERNS = {
        "ssn": r'\b\d{3}-\d{2}-\d{4}\b',
        "credit_card": r'\b\d{16}\b|\b\d{4}[\s-]\d{4}[\s-]\d{4}[\s-]\d{4}\b',
        "email": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        "phone": r'\b\+?\d{1,3}[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{1,4}[-.\s]?\d{1,9}\b',
        "ip_address": r'\b(?:\d{1,3}\.){3}\d{1,3}\b',
        "passport": r'\b[A-Z]{1,2}\d{6,9}\b',
    }

    # Domain whitelist (trusted sources)
    DOMAIN_WHITELIST = [
        "techcrunch.com",
        "wired.com",
        "theverge.com",
        "arstechnica.com",
        "reuters.com",
        "bloomberg.com",
        "wsj.com",
        "nytimes.com",
        "bbc.com",
        "cnn.com",
        "tass.ru",
        "rbc.ru",
        "vedomosti.ru",
        "kommersant.ru"
    ]

    # Domain blacklist (known spam/malicious)
    DOMAIN_BLACKLIST = [
        "spam.com",
        "phishing.net",
        "malware.org",
        "scam.com"
    ]

    @staticmethod
    def mask_pii(text: str, mask_char: str = "[REDACTED]") -> str:
        """
        Automatically mask PII in text

        Args:
            text: Input text
            mask_char: Replacement string for PII

        Returns:
            Text with PII masked
        """
        masked = text

        for pii_type, pattern in PIIMasker.PII_PATTERNS.items():
            masked = re.sub(pattern, f"{mask_char}_{pii_type.upper()}", masked, flags=re.IGNORECASE)

        return masked

    @staticmethod
    def contains_pii(text: str) -> bool:
        """
        Check if text contains PII

        Args:
            text: Input text

        Returns:
            True if PII detected
        """
        for pattern in PIIMasker.PII_PATTERNS.values():
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False

    @staticmethod
    def detect_pii_types(text: str) -> List[str]:
        """
        Detect which types of PII are present

        Args:
            text: Input text

        Returns:
            List of PII types found
        """
        detected = []

        for pii_type, pattern in PIIMasker.PII_PATTERNS.items():
            if re.search(pattern, text, re.IGNORECASE):
                detected.append(pii_type)

        return detected

    @staticmethod
    def validate_domain_trust(url: Optional[str]) -> float:
        """
        Calculate trust score for domain

        Args:
            url: URL to check

        Returns:
            Trust score: 1.0 (whitelisted), 0.7 (unknown), 0.0 (blacklisted)
        """
        if not url:
            return 0.7  # Neutral for missing URL

        url_lower = url.lower()

        # Check blacklist first
        for domain in PIIMasker.DOMAIN_BLACKLIST:
            if domain in url_lower:
                logger.warning(f"Blacklisted domain detected: {domain}")
                return 0.0

        # Check whitelist
        for domain in PIIMasker.DOMAIN_WHITELIST:
            if domain in url_lower:
                return 1.0

        # Unknown domain - apply penalty
        return 0.7

    @staticmethod
    def is_safe_domain(url: Optional[str]) -> bool:
        """
        Check if domain is safe (not blacklisted)

        Args:
            url: URL to check

        Returns:
            True if safe
        """
        if not url:
            return True

        url_lower = url.lower()

        for domain in PIIMasker.DOMAIN_BLACKLIST:
            if domain in url_lower:
                return False

        return True

    @staticmethod
    def sanitize_evidence(evidence_list: List[Dict]) -> List[Dict]:
        """
        Sanitize evidence list by masking PII and checking domains

        Args:
            evidence_list: List of Evidence dicts

        Returns:
            Sanitized evidence list
        """
        sanitized = []

        for ev in evidence_list:
            # Check domain safety
            if not PIIMasker.is_safe_domain(ev.get("url")):
                logger.warning(f"Skipping evidence from blacklisted domain: {ev.get('url')}")
                continue

            # Mask PII in snippet
            snippet = ev.get("snippet", "")
            if PIIMasker.contains_pii(snippet):
                logger.warning(f"PII detected in snippet, masking: {ev.get('title')}")
                ev["snippet"] = PIIMasker.mask_pii(snippet)

            # Mask PII in title
            title = ev.get("title", "")
            if PIIMasker.contains_pii(title):
                logger.warning(f"PII detected in title, masking: {title}")
                ev["title"] = PIIMasker.mask_pii(title)

            sanitized.append(ev)

        return sanitized

    @staticmethod
    def calculate_confidence_penalty(evidence_list: List[Dict]) -> float:
        """
        Calculate confidence penalty based on domain trust

        Args:
            evidence_list: List of Evidence dicts

        Returns:
            Confidence multiplier [0.0, 1.0]
        """
        if not evidence_list:
            return 0.5  # Low confidence for no evidence

        trust_scores = []

        for ev in evidence_list:
            url = ev.get("url")
            trust = PIIMasker.validate_domain_trust(url)
            trust_scores.append(trust)

        # Average trust score
        avg_trust = sum(trust_scores) / len(trust_scores)

        return avg_trust


def create_pii_masker() -> PIIMasker:
    """Factory function to create PII masker"""
    return PIIMasker()
