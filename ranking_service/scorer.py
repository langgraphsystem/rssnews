"""
Production Scoring Engine
Implements weighted scoring: 0.58·S_sem + 0.32·S_fts + 0.06·S_fresh + 0.04·S_source
"""

import os
import math
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ScoringWeights:
    """Production scoring weights configuration"""
    # NEW weights for /ask news mode (Sprint 2)
    semantic: float = 0.45  # Reduced from 0.58
    fts: float = 0.30       # Reduced from 0.32
    freshness: float = 0.20 # Increased from 0.06 (prioritize fresh news)
    source: float = 0.05    # Increased from 0.04

    # Time decay parameters
    tau_hours: int = 72  # General news decay: 72 hours
    tau_hours_evergreen: int = 240  # Evergreen content: 240 hours

    # Domain caps
    max_per_domain: int = 3
    max_per_article: int = 2

    # NEW: Off-topic and category filtering (Sprint 2)
    min_cosine_threshold: float = 0.28  # Drop if similarity < 0.28
    require_dates_in_top_n: bool = True  # Require published_at for top results
    date_penalty_factor: float = 0.3  # Multiply score by 0.3 if no date


@dataclass
class EverGreenWeights:
    """Evergreen content weights (how/analysis/explainer/guide)"""
    semantic: float = 0.62
    fts: float = 0.30
    freshness: float = 0.04
    source: float = 0.04
    tau_hours: int = 240


class ProductionScorer:
    """Production-ready scoring engine with explainability"""

    def __init__(self, weights: Optional[ScoringWeights] = None):
        self.weights = weights or ScoringWeights()
        self.evergreen_weights = EverGreenWeights()
        self.evergreen_triggers = {
            'how', 'analysis', 'explainer', 'guide', 'tutorial',
            'what is', 'why', 'understanding', 'explained'
        }

        # Load from environment if available
        self._load_from_env()

    def _load_from_env(self):
        """Load scoring weights from environment variables"""
        try:
            if os.getenv('SCORING_SEMANTIC_WEIGHT'):
                self.weights.semantic = float(os.getenv('SCORING_SEMANTIC_WEIGHT'))
            if os.getenv('SCORING_FTS_WEIGHT'):
                self.weights.fts = float(os.getenv('SCORING_FTS_WEIGHT'))
            if os.getenv('SCORING_FRESHNESS_WEIGHT'):
                self.weights.freshness = float(os.getenv('SCORING_FRESHNESS_WEIGHT'))
            if os.getenv('SCORING_SOURCE_WEIGHT'):
                self.weights.source = float(os.getenv('SCORING_SOURCE_WEIGHT'))
            if os.getenv('SCORING_TAU_HOURS'):
                self.weights.tau_hours = int(os.getenv('SCORING_TAU_HOURS'))
        except (ValueError, TypeError) as e:
            logger.warning(f"Error loading scoring weights from env: {e}")

    def is_evergreen_query(self, query: str) -> bool:
        """Detect if query is evergreen content focused"""
        query_lower = query.lower()
        return any(trigger in query_lower for trigger in self.evergreen_triggers)

    def calculate_freshness_score(self, published_at: datetime,
                                tau_hours: Optional[int] = None) -> float:
        """Calculate time-based freshness score with exponential decay"""
        if not published_at:
            return 0.0

        tau = tau_hours or self.weights.tau_hours
        from datetime import timezone
        now = datetime.now(timezone.utc)

        # Handle timezone-naive datetimes - make both timezone-aware or both naive
        if published_at.tzinfo is None:
            # If published_at is naive, make now naive too
            now = now.replace(tzinfo=None)
        elif now.tzinfo is None:
            # If published_at is aware but now is naive, make now aware
            now = now.replace(tzinfo=timezone.utc)

        age_hours = (now - published_at).total_seconds() / 3600

        # Exponential decay: e^(-age/τ)
        freshness = math.exp(-age_hours / tau)
        return min(1.0, max(0.0, freshness))

    def calculate_source_score(self, domain: str,
                             source_score: Optional[float] = None) -> float:
        """Calculate source authority score"""
        if source_score is not None:
            return max(0.0, min(1.0, source_score))

        # Default source scores for known domains
        authority_scores = {
            'reuters.com': 0.85,
            'ap.org': 0.85,
            'bbc.com': 0.80,
            'nytimes.com': 0.78,
            'theguardian.com': 0.75,
            'washingtonpost.com': 0.75,
            'cnn.com': 0.70,
            'bloomberg.com': 0.75,
            'wsj.com': 0.78,
            'economist.com': 0.80,
        }

        return authority_scores.get(domain.lower(), 0.5)  # Default neutral

    def normalize_scores(self, scores: List[float]) -> List[float]:
        """Min-max normalization of scores to [0,1]"""
        if not scores or len(scores) <= 1:
            return scores

        min_score = min(scores)
        max_score = max(scores)

        if max_score == min_score:
            return [0.5] * len(scores)  # All equal -> neutral

        return [(score - min_score) / (max_score - min_score) for score in scores]

    def score_results(self, results: List[Dict[str, Any]],
                     query: str) -> List[Dict[str, Any]]:
        """Apply production scoring to search results"""
        if not results:
            return results

        # Determine if evergreen query
        is_evergreen = self.is_evergreen_query(query)
        active_weights = self.evergreen_weights if is_evergreen else self.weights

        logger.info(f"Scoring {len(results)} results with {'evergreen' if is_evergreen else 'general'} weights")

        # Extract and normalize individual scores
        semantic_scores = []
        fts_scores = []

        for result in results:
            # Semantic similarity (cosine similarity from pgvector)
            sem_score = result.get('similarity', result.get('semantic_score', 0.5))
            semantic_scores.append(float(sem_score))

            # FTS score (ts_rank from PostgreSQL)
            fts_score = result.get('fts_rank', result.get('fts_score', 0.5))
            fts_scores.append(float(fts_score))

        # Normalize scores
        semantic_scores = self.normalize_scores(semantic_scores)
        fts_scores = self.normalize_scores(fts_scores)

        # Calculate final scores
        scored_results = []
        for i, result in enumerate(results):
            # Get normalized component scores
            s_sem = semantic_scores[i]
            s_fts = fts_scores[i]

            # Calculate freshness score
            published_at = result.get('published_at')
            if isinstance(published_at, str):
                try:
                    published_at = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
                except:
                    published_at = None

            tau = active_weights.tau_hours if is_evergreen else self.weights.tau_hours
            s_fresh = self.calculate_freshness_score(published_at, tau)

            # Calculate source score
            domain = result.get('source_domain', result.get('domain', result.get('source', '')))
            s_source = self.calculate_source_score(domain, result.get('source_score'))

            # Final weighted score
            final_score = (
                active_weights.semantic * s_sem +
                active_weights.fts * s_fts +
                active_weights.freshness * s_fresh +
                active_weights.source * s_source
            )

            # Add scoring metadata
            scoring_info = {
                'scores': {
                    'semantic': round(s_sem, 4),
                    'fts': round(s_fts, 4),
                    'freshness': round(s_fresh, 4),
                    'source': round(s_source, 4),
                    'final': round(final_score, 4)
                },
                'weights_used': 'evergreen' if is_evergreen else 'general',
                'tau_hours': tau,
                'postflags': {}
            }

            result_copy = result.copy()
            result_copy.update(scoring_info)
            scored_results.append(result_copy)

        # Sort by final score (descending)
        scored_results.sort(key=lambda x: x['scores']['final'], reverse=True)

        return scored_results

    def apply_domain_caps(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Apply domain and article caps to prevent over-representation"""
        if not results:
            return results

        domain_counts = {}
        article_counts = {}
        capped_results = []

        for result in results:
            domain = result.get('source_domain', result.get('domain', result.get('source', 'unknown')))
            article_id = result.get('article_id', result.get('id'))

            # Check domain cap
            domain_count = domain_counts.get(domain, 0)
            if domain_count >= self.weights.max_per_domain:
                result['postflags']['domain_capped'] = True
                continue

            # Check article cap
            if article_id:
                article_count = article_counts.get(article_id, 0)
                if article_count >= self.weights.max_per_article:
                    result['postflags']['article_capped'] = True
                    continue
                article_counts[article_id] = article_count + 1

            domain_counts[domain] = domain_count + 1
            capped_results.append(result)

        logger.info(f"Applied caps: {len(results)} -> {len(capped_results)} results")
        return capped_results

    def calculate_penalties(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Apply penalties for duplicates and near-duplicates"""
        if not results:
            return results

        penalized_results = []
        seen_titles = set()
        seen_content_hashes = set()

        for result in results:
            penalty_factor = 1.0
            flags = result.get('postflags', {})

            # Title similarity penalty
            title = result.get('title_norm', result.get('title', '')).lower().strip()
            if title in seen_titles:
                penalty_factor *= 0.8
                flags['duplicate_title_penalty'] = True
            else:
                seen_titles.add(title)

            # Content hash penalty
            content_hash = result.get('content_hash')
            if content_hash and content_hash in seen_content_hashes:
                penalty_factor *= 0.6
                flags['duplicate_content_penalty'] = True
            elif content_hash:
                seen_content_hashes.add(content_hash)

            # Apply penalty to final score
            if penalty_factor < 1.0:
                original_score = result['scores']['final']
                result['scores']['final'] = original_score * penalty_factor
                flags['penalty_factor'] = penalty_factor

            result['postflags'] = flags
            penalized_results.append(result)

        return penalized_results

    def filter_offtopic(self, results: List[Dict[str, Any]],
                       query: str,
                       threshold: Optional[float] = None) -> Tuple[List[Dict[str, Any]], int]:
        """
        Filter off-topic articles using cosine similarity threshold

        Args:
            results: List of search results with semantic scores
            query: Original query string
            threshold: Minimum cosine similarity (default from weights)

        Returns:
            Tuple of (filtered_results, dropped_count)
        """
        if not results:
            return results, 0

        min_threshold = threshold or self.weights.min_cosine_threshold
        filtered_results = []
        dropped_count = 0

        for result in results:
            # Check semantic similarity (cosine from pgvector)
            similarity = result.get('similarity', result.get('semantic_score', 1.0))

            if similarity < min_threshold:
                # Mark as off-topic and drop
                result.get('postflags', {})['offtopic_dropped'] = True
                result.get('postflags', {})['drop_reason'] = f'similarity={similarity:.3f} < {min_threshold}'
                dropped_count += 1
                logger.debug(
                    f"Dropped off-topic: '{result.get('title', 'N/A')[:50]}...' "
                    f"(similarity={similarity:.3f})"
                )
            else:
                filtered_results.append(result)

        if dropped_count > 0:
            logger.info(f"Off-topic guard: dropped {dropped_count}/{len(results)} articles")

        return filtered_results, dropped_count

    def apply_category_penalties(self, results: List[Dict[str, Any]],
                                 intent: str = "news_current_events") -> List[Dict[str, Any]]:
        """
        Apply category-based penalties for irrelevant content types

        Categories penalized for news queries:
        - Sports: -50% (unless query explicitly about sports)
        - Entertainment/Celebrity: -40%
        - Crime/Local incidents: -30%
        - Weather: -20%

        Args:
            results: List of search results
            intent: Query intent (general_qa or news_current_events)

        Returns:
            Results with category penalties applied
        """
        if not results or intent != "news_current_events":
            return results

        # Category keywords and penalty factors
        category_penalties = {
            'sports': {
                'keywords': ['game', 'match', 'score', 'playoff', 'championship', 'league',
                           'football', 'basketball', 'baseball', 'soccer', 'tennis',
                           'nfl', 'nba', 'mlb', 'uefa', 'fifa'],
                'penalty': 0.5,  # -50%
            },
            'entertainment': {
                'keywords': ['celebrity', 'movie', 'film', 'actor', 'actress', 'hollywood',
                           'oscars', 'grammy', 'emmy', 'music video', 'album', 'concert'],
                'penalty': 0.6,  # -40%
            },
            'crime': {
                'keywords': ['arrest', 'charged', 'suspect', 'robbery', 'theft', 'murder',
                           'shooting', 'stabbing', 'assault', 'police arrest'],
                'penalty': 0.7,  # -30%
            },
            'weather': {
                'keywords': ['forecast', 'temperature', 'rain', 'snow', 'storm warning',
                           'weather alert', 'high of', 'low of'],
                'penalty': 0.8,  # -20%
            },
        }

        penalized_results = []
        penalties_applied = 0

        for result in results:
            title = result.get('title', '').lower()
            snippet = result.get('snippet', result.get('text', ''))[:200].lower()
            combined_text = f"{title} {snippet}"

            # Check each category
            applied_penalty = None
            for category, config in category_penalties.items():
                # Count keyword matches
                matches = sum(1 for keyword in config['keywords'] if keyword in combined_text)

                # Apply penalty if 2+ keywords match
                if matches >= 2:
                    penalty_factor = config['penalty']
                    original_score = result.get('scores', {}).get('final', 0.5)
                    result['scores']['final'] = original_score * penalty_factor

                    # Add flag
                    flags = result.get('postflags', {})
                    flags[f'{category}_penalty'] = True
                    flags['category_penalty_factor'] = penalty_factor
                    result['postflags'] = flags

                    applied_penalty = category
                    penalties_applied += 1
                    logger.debug(
                        f"Category penalty ({category}): '{title[:50]}...' "
                        f"(factor={penalty_factor}, matches={matches})"
                    )
                    break  # Only apply one category penalty

            penalized_results.append(result)

        if penalties_applied > 0:
            logger.info(f"Category penalties: applied to {penalties_applied}/{len(results)} articles")

        return penalized_results

    def apply_date_penalties(self, results: List[Dict[str, Any]],
                            require_dates: bool = None) -> List[Dict[str, Any]]:
        """
        Apply penalties for missing publication dates

        Args:
            results: List of search results
            require_dates: Whether to require dates (default from weights)

        Returns:
            Results with date penalties applied
        """
        if not results:
            return results

        require = require_dates if require_dates is not None else self.weights.require_dates_in_top_n
        penalty_factor = self.weights.date_penalty_factor

        penalized_results = []
        no_date_count = 0

        for result in results:
            published_at = result.get('published_at')

            # Check if date is missing or invalid
            has_date = bool(published_at)
            if isinstance(published_at, str):
                if published_at in ['None', '', 'null']:
                    has_date = False

            if not has_date and require:
                # Apply strong penalty
                original_score = result.get('scores', {}).get('final', 0.5)
                result['scores']['final'] = original_score * penalty_factor

                # Add flag
                flags = result.get('postflags', {})
                flags['no_date_penalty'] = True
                flags['date_penalty_factor'] = penalty_factor
                result['postflags'] = flags

                no_date_count += 1
                logger.debug(
                    f"Date penalty: '{result.get('title', 'N/A')[:50]}...' "
                    f"(factor={penalty_factor})"
                )

            penalized_results.append(result)

        if no_date_count > 0:
            logger.info(f"Date penalties: applied to {no_date_count}/{len(results)} articles without dates")

        return penalized_results

    def score_and_rank(self, results: List[Dict[str, Any]],
                      query: str,
                      apply_caps: bool = True,
                      intent: str = "news_current_events",
                      filter_offtopic: bool = True,
                      apply_category_penalties: bool = True,
                      apply_date_penalties: bool = True) -> List[Dict[str, Any]]:
        """
        Complete scoring pipeline with filtering and penalties

        NEW Sprint 2 features:
        - Off-topic filtering (cosine < 0.28)
        - Category penalties (sports/entertainment/crime)
        - Date penalties (missing published_at)
        """
        if not results:
            return results

        # Step 1: Filter off-topic articles
        if filter_offtopic:
            results, dropped = self.filter_offtopic(results, query)
            if dropped > 0:
                logger.info(f"Off-topic filter: {dropped} articles dropped")

        # Step 2: Calculate base scores
        scored_results = self.score_results(results, query)

        # Step 3: Apply category penalties (NEW Sprint 2)
        if apply_category_penalties:
            scored_results = self.apply_category_penalties(scored_results, intent)

        # Step 4: Apply date penalties (NEW Sprint 2)
        if apply_date_penalties:
            scored_results = self.apply_date_penalties(scored_results)

        # Step 5: Apply duplicate penalties
        penalized_results = self.calculate_penalties(scored_results)

        # Step 6: Apply domain caps
        if apply_caps:
            final_results = self.apply_domain_caps(penalized_results)
        else:
            final_results = penalized_results

        # Step 7: Final sort by adjusted scores
        final_results.sort(key=lambda x: x['scores']['final'], reverse=True)

        logger.info(f"Scoring complete: {len(results)} -> {len(final_results)} final results")
        return final_results