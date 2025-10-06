"""
Intent Router for /ask Command
Classifies queries as general_qa vs news_current_events
"""

import re
import logging
from typing import Literal
from dataclasses import dataclass

logger = logging.getLogger(__name__)

QueryIntent = Literal["general_qa", "news_current_events"]


@dataclass
class IntentClassification:
    """Result of intent classification"""
    intent: QueryIntent
    confidence: float
    reason: str


class IntentRouter:
    """
    Lightweight intent router using regex + heuristics
    Routes queries to appropriate handling path
    """

    def __init__(self):
        # General-QA triggers (knowledge/explanation questions)
        self.general_qa_patterns = [
            r'^\s*(what|how|why|difference|define|explain|meaning|definition|compare)',
            r'\b(what is|what are|how does|how do|why is|why does)\b',
            r'\b(difference between|comparison|versus|vs\.?)\b',
            r'\b(define|definition|meaning of|explanation)\b',
        ]

        # News/current events triggers
        self.news_patterns = [
            r'\b(today|yesterday|this week|last week|this month)\b',
            r'\b(latest|recent|update|updates|breaking|current)\b',
            r'\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{1,2}',
            r'\b20[0-9]{2}\b',  # Year mentions
            r'\b(announced|announced today|reported|happened)\b',
        ]

        # Russian temporal indicators
        self.russian_news_patterns = [
            r'\b(сегодня|вчера|на этой неделе|в этом месяце)\b',
            r'\b(последние|недавние|обновления|новости)\b',
        ]

        # Force news if query contains search operators
        self.search_operator_pattern = r'\b(site:|after:|before:)\S+'

        # Named entity indicators (simple heuristics)
        self.entity_patterns = [
            r'\b[A-Z][a-z]+\s+[A-Z][a-z]+\b',  # Capitalized names (2+ words)
            r'\b(israel|hamas|ukraine|russia|china|eu|us|uk)\b',
            r'\b(government|parliament|congress|senate|president)\b',
            r'\b(ceasefire|regulation|law|act|policy|treaty)\b',
        ]

    def classify(self, query: str) -> IntentClassification:
        """
        Classify query intent

        Args:
            query: User query string

        Returns:
            IntentClassification with intent, confidence, and reason
        """
        query_lower = query.lower()

        # RULE 1: Search operators force news mode
        if re.search(self.search_operator_pattern, query, re.IGNORECASE):
            logger.info(f"Intent: news_current_events (search operators detected)")
            return IntentClassification(
                intent="news_current_events",
                confidence=1.0,
                reason="search_operators (site:/after:/before:)"
            )

        # RULE 2: Check for general-QA patterns (high priority)
        general_qa_matches = sum(
            1 for pattern in self.general_qa_patterns
            if re.search(pattern, query_lower, re.IGNORECASE)
        )

        # RULE 3: Check for news patterns
        news_matches = sum(
            1 for pattern in (self.news_patterns + self.russian_news_patterns)
            if re.search(pattern, query_lower, re.IGNORECASE)
        )

        # RULE 4: Check for named entities
        entity_matches = sum(
            1 for pattern in self.entity_patterns
            if re.search(pattern, query, re.IGNORECASE)
        )

        # Decision logic
        total_signals = general_qa_matches + news_matches + entity_matches

        if total_signals == 0:
            # No clear signals — default to news if query is short, general-QA if long/complex
            if len(query.split()) <= 4 and any(c.isupper() for c in query):
                # Short query with capitals → likely named entity → news
                logger.info(f"Intent: news_current_events (short query with capitals, default)")
                return IntentClassification(
                    intent="news_current_events",
                    confidence=0.6,
                    reason="default_heuristic (short_with_capitals)"
                )
            else:
                # Longer query without clear signals → general-QA
                logger.info(f"Intent: general_qa (no clear signals, default)")
                return IntentClassification(
                    intent="general_qa",
                    confidence=0.5,
                    reason="default_heuristic (no_clear_signals)"
                )

        # If general-QA patterns dominate and no strong news signals
        if general_qa_matches > 0 and news_matches == 0 and entity_matches == 0:
            logger.info(f"Intent: general_qa (qa_patterns={general_qa_matches})")
            return IntentClassification(
                intent="general_qa",
                confidence=0.9,
                reason=f"qa_patterns_dominant (matches={general_qa_matches})"
            )

        # If news patterns or entities present
        if news_matches > 0 or entity_matches > 0:
            confidence = min(0.95, 0.6 + 0.1 * (news_matches + entity_matches))
            logger.info(
                f"Intent: news_current_events (news_matches={news_matches}, "
                f"entity_matches={entity_matches})"
            )
            return IntentClassification(
                intent="news_current_events",
                confidence=confidence,
                reason=f"news_signals (news={news_matches}, entities={entity_matches})"
            )

        # Mixed signals — prefer news if entities present
        if entity_matches > 0:
            logger.info(f"Intent: news_current_events (mixed signals, entities present)")
            return IntentClassification(
                intent="news_current_events",
                confidence=0.7,
                reason="mixed_signals_with_entities"
            )

        # Default to general-QA if truly ambiguous
        logger.info(f"Intent: general_qa (ambiguous, default)")
        return IntentClassification(
            intent="general_qa",
            confidence=0.5,
            reason="ambiguous_default"
        )


# Singleton instance
_intent_router_instance = None


def get_intent_router() -> IntentRouter:
    """Get singleton intent router instance"""
    global _intent_router_instance
    if _intent_router_instance is None:
        _intent_router_instance = IntentRouter()
    return _intent_router_instance
