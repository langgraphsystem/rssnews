"""
Command Handlers for Advanced Bot Features
Handles complex command processing and state management
"""

import logging
import re
from urllib.parse import urlparse
from collections import Counter
from functools import lru_cache
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple, Set

logger = logging.getLogger(__name__)


class CommandHandler:
    """Handles advanced bot commands and state"""

    def __init__(self, ranking_api, db_client):
        self.ranking_api = ranking_api
        self.db = db_client

        # Command state tracking
        self.command_states = {}  # user_id -> command_state

    # ---------- Generic soft relevance helpers (query-driven) ----------
    @staticmethod
    def _short_domain(url: str) -> str:
        try:
            d = urlparse(url).netloc.lower()
            if d.startswith("www."):
                d = d[4:]
            return d
        except Exception:
            return ""

    @staticmethod
    def _normalize_text(s: Optional[str]) -> str:
        s = (s or "").lower()
        return re.sub(r"[^a-z0-9\/\-\._\s]", " ", s)

    @staticmethod
    def _tokenize(s: str) -> List[str]:
        return [t for t in re.split(r"\s+|[\/\-\._]", s) if t]

    @staticmethod
    def _ngrams(tokens: List[str], n: int) -> Set[str]:
        return {" ".join(tokens[i:i+n]) for i in range(len(tokens)-n+1)} if n > 1 else set(tokens)

    @staticmethod
    def _top_level_domain(domain: str) -> str:
        parts = domain.split(".")
        return parts[-1] if parts else ""

    @staticmethod
    @lru_cache(maxsize=256)
    def _synonyms_for_query(raw_query: str) -> Set[str]:
        q = raw_query.lower()
        synonyms_map = {
            "immigration and customs enforcement": {"dhs ice","immigration enforcement","enforcement and removal operations","ero","homeland security investigations","hsi"},
            "customs and border protection": {"cbp","border patrol","ports of entry"},
            "department of homeland security": {"dhs","homeland security"},
            "supreme court": {"scotus","supreme court of the united states"},
            "federal reserve": {"the fed","us central bank"},
        }
        syns: Set[str] = set()
        for key, vals in synonyms_map.items():
            if key in q:
                syns |= vals
        return syns

    def _build_positive_cues(self, query: str) -> Set[str]:
        qn = self._normalize_text(query)
        toks = self._tokenize(qn)
        cues: Set[str] = set(toks)
        cues |= self._ngrams(toks, 2)
        cues |= self._ngrams(toks, 3)
        cues |= self._synonyms_for_query(query)
        STOP = {"the","a","an","of","and","or","in","on","for","to","with","news","update","today","latest"}
        return {c for c in cues if c and c not in STOP and len(c) > 1}

    def _score_article(self, article: Dict[str, Any], cues: Set[str]) -> Tuple[float, Dict[str, int]]:
        """Return (score, evidence_counts). Higher score => more relevant."""
        title = self._normalize_text(article.get("title"))
        content = self._normalize_text(article.get("content") or article.get("description"))
        url = (article.get("url") or "")
        dom = self._short_domain(url)
        path = self._normalize_text(url)
        ents = [self._normalize_text(e) for e in (article.get("entities") or [])]

        NOISE = {"football","soccer","hockey","forecast","weather","nhl","odds","bet","coupon","promo","recipe","cooking","celebrity","gossip","horoscope"}

        score = 0.0
        ev = Counter()

        for cue in cues:
            if cue in title:
                score += 2.5; ev["title"] += 1
            if cue in content:
                score += 1.5; ev["content"] += 1
            if cue in path:
                score += 1.0; ev["url"] += 1
            if cue and ents and any(cue in e for e in ents):
                score += 1.5; ev["entities"] += 1

        TRUSTED = {"apnews.com","reuters.com","nytimes.com","washingtonpost.com","wsj.com","bbc.com","theguardian.com","npr.org","bloomberg.com","axios.com","politico.com","ft.com"}
        tld = self._top_level_domain(dom)
        if tld in {"gov","edu"}:
            score += 2.0; ev["domain_trusted"] += 1
        if dom in TRUSTED:
            score += 1.5; ev["domain_major_media"] += 1

        text = f"{title}\n{content}"
        if any(n in text for n in NOISE) and score < 2.0:
            score -= 2.0; ev["noise"] += 1

        if any(h in path for h in ("/policy/","/regulation","/court","/law","/case","/immigration","/agency","/press/")):
            score += 0.5; ev["url_hint"] += 1

        return score, ev

    def _soft_relevance_filter(self, query: str, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Generic soft filter: score by cues from query and keep top items.

        - Build cues = tokens + n-grams + synonyms; score by title/content/url/entities.
        - Drop obvious noise; keep top-30 sorted by score; ensure len>=0.
        """
        if not results:
            return results
        cues = self._build_positive_cues(query)
        scored: List[Tuple[float, Dict[str, Any]]] = []
        for r in results:
            s, _ = self._score_article(r, cues)
            r["_soft_score"] = s
            scored.append((s, r))
        kept = [r for (s, r) in scored if s >= 0.5]
        if len(kept) < 30:
            kept = [r for (s, r) in sorted(scored, key=lambda x: x[0], reverse=True)[:30]]
        else:
            kept = sorted(kept, key=lambda x: x.get("_soft_score", 0), reverse=True)[:30]
        return kept

    def _update_command_state(self, user_id: str, state: Dict[str, Any]):
        """Update user command state"""
        self.command_states[user_id] = {
            **state,
            'updated_at': datetime.utcnow()
        }

    def _get_command_state(self, user_id: str) -> Dict[str, Any]:
        """Get user command state"""
        return self.command_states.get(user_id, {})

    def _clear_command_state(self, user_id: str):
        """Clear user command state"""
        if user_id in self.command_states:
            del self.command_states[user_id]

    async def handle_multi_step_search(self, user_id: str, step_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle multi-step search refinement"""
        try:
            state = self._get_command_state(user_id)

            if not state.get('base_query'):
                return {'error': 'No base search query found'}

            # Build refined search request
            from ranking_api import SearchRequest

            filters = {}

            # Apply time filter
            if step_data.get('time_range'):
                filters['time_range'] = step_data['time_range']

            # Apply source filter
            if step_data.get('sources'):
                filters['sources'] = step_data['sources']

            # Create refined request
            search_request = SearchRequest(
                query=state['base_query'],
                method=step_data.get('method', 'hybrid'),
                limit=step_data.get('limit', 10),
                filters=filters,
                user_id=user_id,
                explain=True
            )

            # Execute search
            response = await self.ranking_api.search(search_request)

            # Update state
            self._update_command_state(user_id, {
                **state,
                'last_search': response,
                'last_filters': filters
            })

            return {
                'success': True,
                'response': response,
                'applied_filters': filters
            }

        except Exception as e:
            logger.error(f"Multi-step search failed: {e}")
            return {'error': str(e)}

    async def handle_source_filtering(self, user_id: str, sources: List[str]) -> Dict[str, Any]:
        """Handle source-based filtering"""
        try:
            state = self._get_command_state(user_id)

            if not state.get('base_query'):
                return {'error': 'No base search query found'}

            # Get domain profiles for sources
            domain_profiles = []
            for source in sources:
                profile = self.db.get_domain_profile(source)
                if profile:
                    domain_profiles.append(profile)

            # Execute filtered search
            from ranking_api import SearchRequest

            search_request = SearchRequest(
                query=state['base_query'],
                method='hybrid',
                limit=15,
                filters={'sources': sources},
                user_id=user_id,
                explain=True
            )

            response = await self.ranking_api.search(search_request)

            return {
                'success': True,
                'response': response,
                'domain_profiles': domain_profiles,
                'filtered_sources': sources
            }

        except Exception as e:
            logger.error(f"Source filtering failed: {e}")
            return {'error': str(e)}

    async def handle_time_filtering(self, user_id: str, time_range: str) -> Dict[str, Any]:
        """Handle time-based filtering"""
        try:
            state = self._get_command_state(user_id)

            if not state.get('base_query'):
                return {'error': 'No base search query found'}

            # Execute time-filtered search
            from ranking_api import SearchRequest

            search_request = SearchRequest(
                query=state['base_query'],
                method='hybrid',
                limit=15,
                filters={'time_range': time_range},
                user_id=user_id,
                explain=True
            )

            response = await self.ranking_api.search(search_request)

            # Analyze temporal distribution
            temporal_analysis = self._analyze_temporal_distribution(response.results)

            return {
                'success': True,
                'response': response,
                'time_range': time_range,
                'temporal_analysis': temporal_analysis
            }

        except Exception as e:
            logger.error(f"Time filtering failed: {e}")
            return {'error': str(e)}

    def _analyze_temporal_distribution(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze temporal distribution of results"""
        try:
            if not results:
                return {}

            timestamps = []
            for result in results:
                pub_date = result.get('published_at')
                if pub_date:
                    try:
                        if isinstance(pub_date, str):
                            timestamp = datetime.fromisoformat(pub_date.replace('Z', '+00:00'))
                        else:
                            timestamp = pub_date
                        timestamps.append(timestamp)
                    except:
                        continue

            if not timestamps:
                return {}

            timestamps.sort()
            now = datetime.utcnow().replace(tzinfo=None)

            # Calculate distribution
            time_buckets = {
                'last_hour': 0,
                'last_6h': 0,
                'last_24h': 0,
                'last_week': 0,
                'older': 0
            }

            for timestamp in timestamps:
                if timestamp.tzinfo:
                    timestamp = timestamp.replace(tzinfo=None)

                hours_ago = (now - timestamp).total_seconds() / 3600

                if hours_ago <= 1:
                    time_buckets['last_hour'] += 1
                elif hours_ago <= 6:
                    time_buckets['last_6h'] += 1
                elif hours_ago <= 24:
                    time_buckets['last_24h'] += 1
                elif hours_ago <= 168:  # 1 week
                    time_buckets['last_week'] += 1
                else:
                    time_buckets['older'] += 1

            return {
                'total_articles': len(timestamps),
                'date_range': {
                    'earliest': timestamps[0].isoformat(),
                    'latest': timestamps[-1].isoformat()
                },
                'distribution': time_buckets
            }

        except Exception as e:
            logger.error(f"Temporal analysis failed: {e}")
            return {}

    async def handle_semantic_expansion(self, user_id: str, query: str) -> Dict[str, Any]:
        """Handle semantic query expansion"""
        try:
            # Get related terms through semantic search
            from ranking_api import SearchRequest

            # First, do a broad semantic search
            search_request = SearchRequest(
                query=query,
                method='semantic',
                limit=20,
                user_id=user_id
            )

            response = await self.ranking_api.search(search_request)

            if not response.results:
                return {'error': 'No semantic matches found'}

            # Extract key terms from results
            key_terms = self._extract_semantic_terms(response.results, query)

            # Generate expanded queries
            expanded_queries = self._generate_expanded_queries(query, key_terms)

            return {
                'success': True,
                'original_query': query,
                'key_terms': key_terms,
                'expanded_queries': expanded_queries,
                'semantic_results': response.results[:5]
            }

        except Exception as e:
            logger.error(f"Semantic expansion failed: {e}")
            return {'error': str(e)}

    def _extract_semantic_terms(self, results: List[Dict[str, Any]], query: str) -> List[str]:
        """Extract semantically related terms from results"""
        try:
            term_frequency = {}
            query_terms = set(query.lower().split())

            for result in results:
                # Get title and text
                title = result.get('title_norm', result.get('title', ''))
                text = result.get('text', result.get('clean_text', ''))

                # Extract terms from title (higher weight)
                title_terms = [t.lower() for t in title.split() if len(t) > 3 and t.lower() not in query_terms]
                for term in title_terms:
                    term_frequency[term] = term_frequency.get(term, 0) + 3

                # Extract terms from text
                text_terms = [t.lower() for t in text.split()[:100] if len(t) > 3 and t.lower() not in query_terms]
                for term in text_terms:
                    term_frequency[term] = term_frequency.get(term, 0) + 1

            # Sort by frequency and return top terms
            sorted_terms = sorted(term_frequency.items(), key=lambda x: x[1], reverse=True)
            return [term for term, freq in sorted_terms[:10] if freq >= 2]

        except Exception as e:
            logger.error(f"Term extraction failed: {e}")
            return []

    def _generate_expanded_queries(self, original_query: str, key_terms: List[str]) -> List[str]:
        """Generate expanded query variations"""
        try:
            expanded = []

            # Add single term expansions
            for term in key_terms[:5]:
                expanded.append(f"{original_query} {term}")

            # Add semantic clusters
            if len(key_terms) >= 2:
                expanded.append(f"{original_query} {' '.join(key_terms[:2])}")

            # Add question forms
            if not original_query.startswith(('what', 'how', 'why', 'when', 'where')):
                expanded.append(f"what is {original_query}")
                if key_terms:
                    expanded.append(f"how does {original_query} relate to {key_terms[0]}")

            return expanded[:5]

        except Exception as e:
            logger.error(f"Query expansion failed: {e}")
            return []

    async def handle_comparison_search(self, user_id: str, entities: List[str]) -> Dict[str, Any]:
        """Handle comparison between entities/topics"""
        try:
            if len(entities) < 2:
                return {'error': 'Need at least 2 entities to compare'}

            comparison_results = {}

            # Search for each entity
            for entity in entities:
                from ranking_api import SearchRequest

                search_request = SearchRequest(
                    query=entity,
                    method='hybrid',
                    limit=10,
                    user_id=user_id,
                    explain=True
                )

                response = await self.ranking_api.search(search_request)
                comparison_results[entity] = response

            # Analyze comparison
            comparison_analysis = self._analyze_comparison(comparison_results)

            return {
                'success': True,
                'entities': entities,
                'individual_results': comparison_results,
                'comparison_analysis': comparison_analysis
            }

        except Exception as e:
            logger.error(f"Comparison search failed: {e}")
            return {'error': str(e)}

    def _analyze_comparison(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze comparison between entities"""
        try:
            analysis = {
                'coverage': {},
                'sources': {},
                'recency': {},
                'sentiment_indicators': {}
            }

            for entity, response in results.items():
                if hasattr(response, 'results'):
                    entity_results = response.results

                    # Coverage analysis
                    analysis['coverage'][entity] = len(entity_results)

                    # Source diversity
                    sources = set()
                    for result in entity_results:
                        domain = result.get('source_domain', result.get('domain', 'unknown'))
                        sources.add(domain)
                    analysis['sources'][entity] = len(sources)

                    # Recency analysis
                    recent_count = 0
                    for result in entity_results:
                        pub_date = result.get('published_at')
                        if pub_date:
                            try:
                                if isinstance(pub_date, str):
                                    timestamp = datetime.fromisoformat(pub_date.replace('Z', '+00:00'))
                                else:
                                    timestamp = pub_date

                                if timestamp.tzinfo:
                                    timestamp = timestamp.replace(tzinfo=None)

                                hours_ago = (datetime.utcnow() - timestamp).total_seconds() / 3600
                                if hours_ago <= 24:
                                    recent_count += 1
                            except:
                                continue

                    analysis['recency'][entity] = recent_count

            return analysis

        except Exception as e:
            logger.error(f"Comparison analysis failed: {e}")
            return {}

    def cleanup_old_states(self, hours: int = 6):
        """Clean up old command states"""
        try:
            cutoff = datetime.utcnow() - timedelta(hours=hours)
            expired_users = []

            for user_id, state in self.command_states.items():
                if state.get('updated_at', cutoff) < cutoff:
                    expired_users.append(user_id)

            for user_id in expired_users:
                del self.command_states[user_id]

            if expired_users:
                logger.info(f"Cleaned up {len(expired_users)} expired command states")

        except Exception as e:
            logger.error(f"State cleanup failed: {e}")
