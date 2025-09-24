"""
Explainability Engine
Provides transparent explanations for ranking decisions
"""

import logging
import re
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ExplanationConfig:
    """Configuration for explanation generation"""
    max_keywords: int = 5
    max_entities: int = 3
    keyword_min_length: int = 3
    show_score_breakdown: bool = True
    show_ranking_factors: bool = True


class ExplainabilityEngine:
    """Engine for generating transparent ranking explanations"""

    def __init__(self, config: Optional[ExplanationConfig] = None):
        self.config = config or ExplanationConfig()

        # Common stop words for keyword extraction
        self.stop_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with',
            'by', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had',
            'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'must',
            'this', 'that', 'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they',
            'said', 'says', 'can', 'also', 'said', 'new', 'one', 'two', 'first', 'last',
            'more', 'other', 'some', 'time', 'very', 'when', 'come', 'here', 'how', 'just',
            'like', 'long', 'make', 'many', 'over', 'such', 'take', 'than', 'them', 'well',
            'were', 'news', 'report', 'reports', 'according', 'sources'
        }

        # Entity patterns for simple NER
        self.entity_patterns = {
            'person': r'\b[A-Z][a-z]+ [A-Z][a-z]+\b',
            'organization': r'\b[A-Z][a-z]+ (?:Corp|Inc|Ltd|LLC|Company|Group|Association|Organization)\b',
            'location': r'\b[A-Z][a-z]+(?: [A-Z][a-z]+)?, [A-Z]{2}\b',  # City, State
            'money': r'\$[\d,]+(?:\.\d{2})?(?:\s?(?:million|billion|trillion))?',
            'percent': r'\d+(?:\.\d+)?%',
        }

    def extract_keywords(self, text: str, query: str = None) -> List[str]:
        """Extract relevant keywords from text"""
        if not text:
            return []

        # Clean and tokenize text
        text_lower = text.lower()
        words = re.findall(r'\b[a-zA-Z]+\b', text_lower)

        # Filter out stop words and short words
        keywords = []
        for word in words:
            if (len(word) >= self.config.keyword_min_length and
                word not in self.stop_words and
                word.isalpha()):
                keywords.append(word)

        # Count word frequency
        word_freq = {}
        for word in keywords:
            word_freq[word] = word_freq.get(word, 0) + 1

        # If query provided, boost query terms
        query_terms = set()
        if query:
            query_terms = set(re.findall(r'\b[a-zA-Z]+\b', query.lower()))
            for term in query_terms:
                if term in word_freq:
                    word_freq[term] *= 3  # Boost query terms

        # Sort by frequency and return top keywords
        sorted_keywords = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
        top_keywords = [word for word, freq in sorted_keywords[:self.config.max_keywords]]

        return top_keywords

    def extract_entities(self, text: str) -> Dict[str, List[str]]:
        """Extract named entities from text using regex patterns"""
        if not text:
            return {}

        entities = {}

        for entity_type, pattern in self.entity_patterns.items():
            matches = re.findall(pattern, text)
            if matches:
                # Remove duplicates and limit count
                unique_matches = list(dict.fromkeys(matches))[:self.config.max_entities]
                if unique_matches:
                    entities[entity_type] = unique_matches

        return entities

    def explain_freshness_score(self, published_at: Optional[datetime],
                               freshness_score: float) -> str:
        """Generate explanation for freshness score"""
        if not published_at or freshness_score == 0:
            return "No publication date available"

        now = datetime.utcnow()
        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=None)
        if now.tzinfo is None:
            now = now.replace(tzinfo=None)

        age_hours = (now - published_at).total_seconds() / 3600

        if age_hours < 1:
            return "Just published (< 1 hour ago)"
        elif age_hours < 24:
            return f"Recent ({int(age_hours)} hours ago)"
        elif age_hours < 168:  # 1 week
            days = int(age_hours / 24)
            return f"Published {days} day{'s' if days > 1 else ''} ago"
        else:
            weeks = int(age_hours / 168)
            return f"Published {weeks} week{'s' if weeks > 1 else ''} ago"

    def explain_source_score(self, domain: str, source_score: float) -> str:
        """Generate explanation for source score"""
        if source_score >= 0.8:
            return f"Highly authoritative source ({domain})"
        elif source_score >= 0.7:
            return f"Well-established source ({domain})"
        elif source_score >= 0.6:
            return f"Reliable source ({domain})"
        elif source_score >= 0.4:
            return f"Standard source ({domain})"
        else:
            return f"Source with limited authority ({domain})"

    def explain_penalties(self, postflags: Dict[str, Any]) -> List[str]:
        """Generate explanations for applied penalties"""
        explanations = []

        if postflags.get('duplicate_title_penalty'):
            explanations.append("Similar title found in results")

        if postflags.get('duplicate_content_penalty'):
            explanations.append("Duplicate content detected")

        if postflags.get('domain_capped'):
            explanations.append("Domain limit reached")

        if postflags.get('article_capped'):
            explanations.append("Article chunk limit reached")

        penalty_factor = postflags.get('penalty_factor')
        if penalty_factor and penalty_factor < 1.0:
            penalty_percent = int((1 - penalty_factor) * 100)
            explanations.append(f"Score reduced by {penalty_percent}% due to penalties")

        return explanations

    def identify_query_matches(self, text: str, query: str) -> List[Dict[str, Any]]:
        """Identify and highlight query matches in text"""
        if not text or not query:
            return []

        # Extract query terms
        query_terms = re.findall(r'\b[a-zA-Z]+\b', query.lower())
        if not query_terms:
            return []

        matches = []
        text_lower = text.lower()

        for term in query_terms:
            # Find all occurrences of the term
            pattern = r'\b' + re.escape(term) + r'\b'
            for match in re.finditer(pattern, text_lower):
                start_pos = match.start()
                end_pos = match.end()

                # Extract context around the match
                context_start = max(0, start_pos - 30)
                context_end = min(len(text), end_pos + 30)
                context = text[context_start:context_end]

                matches.append({
                    'term': term,
                    'position': start_pos,
                    'context': context.strip(),
                    'exact_match': text[start_pos:end_pos]
                })

        # Sort by position and limit to top matches
        matches.sort(key=lambda x: x['position'])
        return matches[:3]  # Top 3 matches

    def generate_explanation(self, result: Dict[str, Any],
                           query: str = None) -> Dict[str, Any]:
        """Generate comprehensive explanation for a search result"""
        explanation = {
            'result_id': result.get('id', result.get('article_id')),
            'why_relevant': [],
            'score_breakdown': {},
            'ranking_factors': [],
            'penalties_applied': [],
            'query_matches': [],
            'content_analysis': {}
        }

        # Score breakdown
        scores = result.get('scores', {})
        if scores and self.config.show_score_breakdown:
            explanation['score_breakdown'] = {
                'final_score': scores.get('final', 0),
                'semantic_similarity': scores.get('semantic', 0),
                'keyword_relevance': scores.get('fts', 0),
                'freshness': scores.get('freshness', 0),
                'source_authority': scores.get('source', 0)
            }

        # Ranking factors explanation
        if self.config.show_ranking_factors:
            factors = []

            if scores.get('semantic', 0) > 0.7:
                factors.append("High semantic similarity to query")
            elif scores.get('semantic', 0) > 0.5:
                factors.append("Good semantic similarity to query")

            if scores.get('fts', 0) > 0.7:
                factors.append("Strong keyword match")
            elif scores.get('fts', 0) > 0.5:
                factors.append("Good keyword relevance")

            if scores.get('freshness', 0) > 0.7:
                factors.append("Recent publication")
            elif scores.get('freshness', 0) > 0.3:
                factors.append("Moderately recent")

            if scores.get('source', 0) > 0.7:
                factors.append("Authoritative source")

            explanation['ranking_factors'] = factors

        # Query matches
        if query:
            text_content = result.get('text', result.get('clean_text', ''))
            title = result.get('title_norm', result.get('title', ''))

            # Check title matches
            title_matches = self.identify_query_matches(title, query)
            text_matches = self.identify_query_matches(text_content, query)

            all_matches = title_matches + text_matches
            explanation['query_matches'] = all_matches[:5]  # Limit to 5 matches

        # Content analysis
        content = result.get('text', result.get('clean_text', ''))
        if content:
            keywords = self.extract_keywords(content, query)
            entities = self.extract_entities(content)

            explanation['content_analysis'] = {
                'key_topics': keywords,
                'entities': entities
            }

        # Penalties explanation
        postflags = result.get('postflags', {})
        if postflags:
            explanation['penalties_applied'] = self.explain_penalties(postflags)

        # Freshness explanation
        published_at = result.get('published_at')
        freshness_score = scores.get('freshness', 0)
        if published_at:
            try:
                if isinstance(published_at, str):
                    pub_date = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
                else:
                    pub_date = published_at

                explanation['freshness_reason'] = self.explain_freshness_score(pub_date, freshness_score)
            except:
                explanation['freshness_reason'] = "Unable to parse publication date"

        # Source explanation
        domain = result.get('source_domain', result.get('domain', result.get('source', '')))
        source_score = scores.get('source', 0)
        if domain:
            explanation['source_reason'] = self.explain_source_score(domain, source_score)

        # Overall relevance summary
        why_relevant = []

        if explanation['query_matches']:
            match_count = len(explanation['query_matches'])
            why_relevant.append(f"Contains {match_count} query term match{'es' if match_count > 1 else ''}")

        if explanation['content_analysis'].get('key_topics'):
            topics = explanation['content_analysis']['key_topics'][:3]
            why_relevant.append(f"Covers topics: {', '.join(topics)}")

        if scores.get('final', 0) > 0.8:
            why_relevant.append("High overall relevance score")
        elif scores.get('final', 0) > 0.6:
            why_relevant.append("Good overall relevance score")

        explanation['why_relevant'] = why_relevant

        return explanation

    def format_explanation_for_bot(self, explanation: Dict[str, Any]) -> str:
        """Format explanation for Telegram bot display"""
        lines = []

        # Score breakdown
        scores = explanation.get('score_breakdown', {})
        if scores:
            final = scores.get('final_score', 0)
            lines.append(f"📊 **Overall Score: {final:.3f}**")
            lines.append("")

            lines.append("**Score Components:**")
            if scores.get('semantic_similarity'):
                lines.append(f"• Semantic: {scores['semantic_similarity']:.3f}")
            if scores.get('keyword_relevance'):
                lines.append(f"• Keywords: {scores['keyword_relevance']:.3f}")
            if scores.get('freshness'):
                lines.append(f"• Freshness: {scores['freshness']:.3f}")
            if scores.get('source_authority'):
                lines.append(f"• Source: {scores['source_authority']:.3f}")
            lines.append("")

        # Why relevant
        why_relevant = explanation.get('why_relevant', [])
        if why_relevant:
            lines.append("**Why This Result:**")
            for reason in why_relevant[:3]:
                lines.append(f"• {reason}")
            lines.append("")

        # Query matches
        matches = explanation.get('query_matches', [])
        if matches:
            lines.append("**Query Matches:**")
            for match in matches[:3]:
                context = match['context'][:60] + "..." if len(match['context']) > 60 else match['context']
                lines.append(f"• '{match['exact_match']}' in: {context}")
            lines.append("")

        # Source and freshness
        if explanation.get('source_reason'):
            lines.append(f"**Source:** {explanation['source_reason']}")

        if explanation.get('freshness_reason'):
            lines.append(f"**Timing:** {explanation['freshness_reason']}")

        # Penalties
        penalties = explanation.get('penalties_applied', [])
        if penalties:
            lines.append("")
            lines.append("**Adjustments:**")
            for penalty in penalties:
                lines.append(f"• {penalty}")

        return "\n".join(lines)

    def bulk_explain(self, results: List[Dict[str, Any]],
                    query: str = None) -> List[Dict[str, Any]]:
        """Generate explanations for multiple results"""
        explanations = []

        for result in results:
            try:
                explanation = self.generate_explanation(result, query)
                explanations.append(explanation)
            except Exception as e:
                logger.error(f"Error generating explanation for result {result.get('id')}: {e}")
                explanations.append({'error': str(e)})

        return explanations