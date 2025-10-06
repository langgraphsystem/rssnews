"""
Query Parser for /ask Command
Extracts search operators: site:, after:, before:, time windows
"""

import re
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ParsedQuery:
    """Parsed query with extracted components"""
    clean_query: str  # Query with operators removed
    domains: List[str]  # From site: operator
    after_date: Optional[datetime]  # From after: operator
    before_date: Optional[datetime]  # From before: operator
    time_window: Optional[str]  # Extracted time window (24h, 7d, etc.)
    original_query: str  # Original input


class QueryParser:
    """
    Parse search query and extract operators
    Supports: site:, after:, before:, time windows
    """

    # Domain allow-list for site: operator
    ALLOWED_DOMAINS = {
        # News
        'reuters.com', 'ap.org', 'bbc.com', 'bbc.co.uk',
        'cnn.com', 'nytimes.com', 'theguardian.com', 'washingtonpost.com',
        'wsj.com', 'bloomberg.com', 'economist.com', 'npr.org',
        'abcnews.go.com', 'cbsnews.com', 'nbcnews.com',
        'ft.com', 'aljazeera.com', 'dw.com',

        # Government/Official
        'europa.eu', 'ec.europa.eu', 'gov.uk', 'whitehouse.gov',
        'state.gov', 'defense.gov', 'justice.gov',
        'un.org', 'who.int', 'imf.org', 'worldbank.org',

        # Tech
        'techcrunch.com', 'theverge.com', 'arstechnica.com', 'wired.com',
        'engadget.com', 'zdnet.com', 'cnet.com',

        # Finance
        'marketwatch.com', 'cnbc.com', 'forbes.com', 'fortune.com',
        'businessinsider.com', 'seekingalpha.com',

        # Russian
        'tass.ru', 'ria.ru', 'interfax.ru', 'kommersant.ru',
        'vedomosti.ru', 'rbc.ru',
    }

    def __init__(self):
        # Regex patterns
        self.site_pattern = re.compile(r'\bsite:(\S+)', re.IGNORECASE)
        self.after_pattern = re.compile(r'\bafter:(\S+)', re.IGNORECASE)
        self.before_pattern = re.compile(r'\bbefore:(\S+)', re.IGNORECASE)

        # Time window patterns
        self.window_pattern = re.compile(
            r'\b(today|yesterday|this week|last week|24h?|7d|14d|30d|1w|2w|1m)\b',
            re.IGNORECASE
        )

        # Russian time patterns
        self.russian_window_pattern = re.compile(
            r'\b(сегодня|вчера|на этой неделе)\b',
            re.IGNORECASE
        )

    def parse(self, query: str) -> ParsedQuery:
        """
        Parse query and extract all components

        Args:
            query: Raw user query

        Returns:
            ParsedQuery with extracted components
        """
        original = query
        clean = query

        # Extract site: domains
        domains = self._extract_domains(clean)
        clean = self.site_pattern.sub('', clean)

        # Extract after: date
        after_date = self._extract_after_date(clean)
        clean = self.after_pattern.sub('', clean)

        # Extract before: date
        before_date = self._extract_before_date(clean)
        clean = self.before_pattern.sub('', clean)

        # Extract time window
        time_window = self._extract_time_window(clean)

        # Clean up whitespace
        clean = ' '.join(clean.split())

        logger.info(
            f"Parsed query: domains={domains}, after={after_date}, before={before_date}, "
            f"window={time_window}, clean='{clean[:50]}...'"
        )

        return ParsedQuery(
            clean_query=clean,
            domains=domains,
            after_date=after_date,
            before_date=before_date,
            time_window=time_window,
            original_query=original
        )

    def _extract_domains(self, query: str) -> List[str]:
        """Extract and validate domains from site: operator"""
        matches = self.site_pattern.findall(query)
        valid_domains = []

        for domain in matches:
            # Clean domain
            domain = domain.lower().strip()
            domain = re.sub(r'[<>\"\'()]', '', domain)

            # Check if in allow-list
            if domain in self.ALLOWED_DOMAINS:
                valid_domains.append(domain)
                logger.info(f"Valid site: domain found: {domain}")
            else:
                # Check if subdomain of allowed domain
                for allowed in self.ALLOWED_DOMAINS:
                    if domain.endswith('.' + allowed) or domain == allowed:
                        valid_domains.append(allowed)  # Use parent domain
                        logger.info(f"Subdomain {domain} → parent {allowed}")
                        break
                else:
                    logger.warning(f"Domain not in allow-list: {domain}")

        return list(set(valid_domains))  # Deduplicate

    def _extract_after_date(self, query: str) -> Optional[datetime]:
        """Extract date from after: operator"""
        match = self.after_pattern.search(query)
        if not match:
            return None

        date_str = match.group(1)
        return self._parse_date(date_str, "after")

    def _extract_before_date(self, query: str) -> Optional[datetime]:
        """Extract date from before: operator"""
        match = self.before_pattern.search(query)
        if not match:
            return None

        date_str = match.group(1)
        return self._parse_date(date_str, "before")

    def _parse_date(self, date_str: str, operator: str) -> Optional[datetime]:
        """
        Parse date string in various formats

        Supports:
        - YYYY-MM-DD
        - YYYY/MM/DD
        - MM/DD/YYYY
        - Relative: 3d, 1w, 2m
        """
        date_str = date_str.strip()

        # Relative dates (3d, 1w, 2m)
        relative_match = re.match(r'^(\d+)([dwmy])$', date_str, re.IGNORECASE)
        if relative_match:
            value = int(relative_match.group(1))
            unit = relative_match.group(2).lower()

            if unit == 'd':
                delta = timedelta(days=value)
            elif unit == 'w':
                delta = timedelta(weeks=value)
            elif unit == 'm':
                delta = timedelta(days=value * 30)  # Approximate
            elif unit == 'y':
                delta = timedelta(days=value * 365)  # Approximate
            else:
                return None

            result = datetime.utcnow() - delta
            logger.info(f"{operator}: relative date {date_str} → {result.date()}")
            return result

        # Absolute dates
        formats = [
            '%Y-%m-%d',
            '%Y/%m/%d',
            '%m/%d/%Y',
            '%d.%m.%Y',
        ]

        for fmt in formats:
            try:
                result = datetime.strptime(date_str, fmt)
                logger.info(f"{operator}: absolute date {date_str} → {result.date()}")
                return result
            except ValueError:
                continue

        logger.warning(f"Could not parse date: {date_str}")
        return None

    def _extract_time_window(self, query: str) -> Optional[str]:
        """
        Extract time window from query

        Returns: 24h, 7d, 14d, 30d, etc.
        """
        # English patterns
        match = self.window_pattern.search(query)
        if match:
            window_str = match.group(1).lower()
            normalized = self._normalize_window(window_str)
            logger.info(f"Time window: {window_str} → {normalized}")
            return normalized

        # Russian patterns
        match = self.russian_window_pattern.search(query)
        if match:
            window_str = match.group(1).lower()
            normalized = self._normalize_russian_window(window_str)
            logger.info(f"Time window (Russian): {window_str} → {normalized}")
            return normalized

        return None

    def _normalize_window(self, window: str) -> str:
        """Normalize time window to standard format"""
        mapping = {
            'today': '24h',
            'yesterday': '24h',
            'this week': '7d',
            'last week': '7d',
            '24h': '24h',
            '24': '24h',
            '7d': '7d',
            '14d': '14d',
            '30d': '30d',
            '1w': '7d',
            '2w': '14d',
            '1m': '30d',
        }
        return mapping.get(window, '7d')  # Default to 7d

    def _normalize_russian_window(self, window: str) -> str:
        """Normalize Russian time window"""
        mapping = {
            'сегодня': '24h',
            'вчера': '24h',
            'на этой неделе': '7d',
        }
        return mapping.get(window, '7d')


# Singleton instance
_query_parser_instance = None


def get_query_parser() -> QueryParser:
    """Get singleton query parser instance"""
    global _query_parser_instance
    if _query_parser_instance is None:
        _query_parser_instance = QueryParser()
    return _query_parser_instance
