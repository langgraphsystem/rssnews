"""
Command Handlers for Advanced Bot Features
Handles complex command processing and state management
"""

import logging
from datetime import datetime
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)


class CommandHandler:
    """Handles advanced bot commands and state"""

    def __init__(self, ranking_api, db_client):
        self.ranking_api = ranking_api
        self.db = db_client

        # Command state tracking
        self.command_states = {}  # user_id -> command_state

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