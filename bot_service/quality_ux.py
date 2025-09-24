"""
Quality UX Handler
Handles explainability, user feedback, and quality improvement features
"""

import logging
import hashlib
from datetime import datetime
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)


class QualityUXHandler:
    """Handles quality UX features like explanations and feedback"""

    def __init__(self, ranking_api, db_client):
        self.ranking_api = ranking_api
        self.db = db_client

        # Session storage for explanations
        self.explanation_sessions = {}  # session_id -> explanation_data

    def _get_session_data(self, session_id: str) -> Dict[str, Any]:
        """Get session data for explanations"""
        return self.explanation_sessions.get(session_id, {})

    def _store_session_data(self, session_id: str, data: Dict[str, Any]):
        """Store session data"""
        self.explanation_sessions[session_id] = {
            **data,
            'timestamp': datetime.utcnow()
        }

    async def handle_explain_request(self, chat_id: str, user_id: str,
                                   session_id: str, message_id: int) -> bool:
        """Handle explanation request for search results"""
        try:
            # Get session data (this would be stored when search was performed)
            session_data = self._get_session_data(session_id)

            if not session_data.get('response'):
                await self._send_message(chat_id, "❌ Session expired. Please search again.")
                return False

            response = session_data['response']

            if not response.explanations:
                await self._send_message(chat_id, "🔄 Generating explanations...")

                # Generate explanations
                explanations = self.ranking_api.explainer.bulk_explain(
                    response.results, response.query_normalized
                )
            else:
                explanations = response.explanations

            # Format explanations
            message = self._format_explanations(explanations[:3], response.query)

            # Create navigation buttons
            buttons = []
            if len(explanations) > 3:
                buttons.append([
                    {"text": "📋 All Explanations", "callback_data": f"explain_all:{session_id}"},
                    {"text": "🔍 Search Tips", "callback_data": f"tips:{session_id}"}
                ])

            buttons.append([
                {"text": "👍 Helpful", "callback_data": f"feedback:helpful:{session_id}"},
                {"text": "👎 Not Helpful", "callback_data": f"feedback:unhelpful:{session_id}"}
            ])

            markup = {"inline_keyboard": buttons} if buttons else None

            return await self._send_message(chat_id, message, markup)

        except Exception as e:
            logger.error(f"Explain request failed: {e}")
            return await self._send_message(chat_id, f"❌ Explanation failed: {e}")

    async def handle_stats_request(self, chat_id: str, user_id: str,
                                 session_id: str, message_id: int) -> bool:
        """Handle statistics request for search results"""
        try:
            session_data = self._get_session_data(session_id)

            if not session_data.get('response'):
                return await self._send_message(chat_id, "❌ Session expired. Please search again.")

            response = session_data['response']

            # Generate statistics
            stats = self._generate_search_statistics(response)
            message = self._format_search_statistics(stats, response)

            # Create buttons
            buttons = [
                [
                    {"text": "📊 Quality Metrics", "callback_data": f"quality_detail:{session_id}"},
                    {"text": "🌐 Source Analysis", "callback_data": f"sources:{session_id}"}
                ],
                [
                    {"text": "⏰ Time Analysis", "callback_data": f"temporal:{session_id}"},
                    {"text": "🔄 Refresh Stats", "callback_data": f"stats:{session_id}"}
                ]
            ]

            markup = {"inline_keyboard": buttons}

            return await self._send_message(chat_id, message, markup)

        except Exception as e:
            logger.error(f"Stats request failed: {e}")
            return await self._send_message(chat_id, f"❌ Statistics failed: {e}")

    async def handle_similar_request(self, chat_id: str, user_id: str,
                                   session_id: str, message_id: int) -> bool:
        """Handle similar/related content request"""
        try:
            session_data = self._get_session_data(session_id)

            if not session_data.get('response'):
                return await self._send_message(chat_id, "❌ Session expired. Please search again.")

            response = session_data['response']

            # Generate related queries based on results
            related_queries = self._generate_related_queries(response)

            if not related_queries:
                return await self._send_message(chat_id, "🤔 No related topics found.")

            message = self._format_related_queries(related_queries, response.query)

            # Create query buttons
            buttons = []
            for i, query in enumerate(related_queries[:6]):
                buttons.append([{
                    "text": f"🔍 {query['title']}",
                    "callback_data": f"search_related:{query['query']}"
                }])

            markup = {"inline_keyboard": buttons}

            return await self._send_message(chat_id, message, markup)

        except Exception as e:
            logger.error(f"Similar request failed: {e}")
            return await self._send_message(chat_id, f"❌ Similar content search failed: {e}")

    async def handle_refine_request(self, chat_id: str, user_id: str,
                                  session_id: str, message_id: int) -> bool:
        """Handle search refinement request"""
        try:
            session_data = self._get_session_data(session_id)

            if not session_data.get('response'):
                return await self._send_message(chat_id, "❌ Session expired. Please search again.")

            response = session_data['response']

            # Generate refinement options
            refinement_options = self._generate_refinement_options(response)

            message = self._format_refinement_options(refinement_options, response.query)

            # Create refinement buttons
            buttons = []

            # Time filters
            time_filters = [
                ("🕐 Last Hour", "refine_time:1h"),
                ("📅 Last Day", "refine_time:24h"),
                ("📆 Last Week", "refine_time:7d")
            ]

            buttons.append([
                {"text": text, "callback_data": f"{callback}:{session_id}"}
                for text, callback in time_filters[:2]
            ])

            buttons.append([
                {"text": time_filters[2][0], "callback_data": f"{time_filters[2][1]}:{session_id}"}
            ])

            # Method refinements
            if response.search_method != 'semantic':
                buttons.append([{
                    "text": "🧠 Semantic Only",
                    "callback_data": f"refine_method:semantic:{session_id}"
                }])

            if response.search_method != 'fts':
                buttons.append([{
                    "text": "🔤 Keywords Only",
                    "callback_data": f"refine_method:fts:{session_id}"
                }])

            markup = {"inline_keyboard": buttons}

            return await self._send_message(chat_id, message, markup)

        except Exception as e:
            logger.error(f"Refine request failed: {e}")
            return await self._send_message(chat_id, f"❌ Refinement failed: {e}")

    def _format_explanations(self, explanations: List[Dict[str, Any]], query: str) -> str:
        """Format explanations for display"""
        lines = []

        lines.append(f"💡 **Why These Results?**")
        lines.append(f"Query: `{self._escape_markdown(query)}`")
        lines.append("")

        for i, explanation in enumerate(explanations, 1):
            lines.append(f"**Result {i}:**")

            # Score breakdown
            scores = explanation.get('score_breakdown', {})
            if scores:
                final = scores.get('final_score', 0)
                lines.append(f"📊 Score: {final:.3f}")

                components = []
                if scores.get('semantic_similarity'):
                    components.append(f"Semantic: {scores['semantic_similarity']:.2f}")
                if scores.get('keyword_relevance'):
                    components.append(f"Keywords: {scores['keyword_relevance']:.2f}")
                if scores.get('freshness'):
                    components.append(f"Fresh: {scores['freshness']:.2f}")

                if components:
                    lines.append(f"   {' • '.join(components)}")

            # Why relevant
            why_relevant = explanation.get('why_relevant', [])
            if why_relevant:
                lines.append(f"✅ {'; '.join(why_relevant[:2])}")

            # Query matches
            matches = explanation.get('query_matches', [])
            if matches:
                match = matches[0]
                context = self._truncate_text(match.get('context', ''), 40)
                lines.append(f"🎯 Found: '{match.get('exact_match', '')}' in {context}")

            lines.append("")

        return "\n".join(lines)

    def _generate_search_statistics(self, response) -> Dict[str, Any]:
        """Generate statistics for search response"""
        try:
            stats = {
                'total_candidates': response.total_results,
                'returned_results': len(response.results),
                'response_time_ms': response.response_time_ms,
                'search_method': response.search_method
            }

            if response.diversity_metrics:
                stats['diversity'] = response.diversity_metrics

            # Analyze sources
            sources = {}
            score_distribution = {'high': 0, 'medium': 0, 'low': 0}
            time_distribution = {'recent': 0, 'moderate': 0, 'old': 0}

            for result in response.results:
                # Source analysis
                domain = result.get('source_domain', result.get('domain', 'unknown'))
                sources[domain] = sources.get(domain, 0) + 1

                # Score analysis
                final_score = result.get('scores', {}).get('final', 0)
                if final_score >= 0.7:
                    score_distribution['high'] += 1
                elif final_score >= 0.4:
                    score_distribution['medium'] += 1
                else:
                    score_distribution['low'] += 1

                # Time analysis
                freshness = result.get('scores', {}).get('freshness', 0)
                if freshness >= 0.7:
                    time_distribution['recent'] += 1
                elif freshness >= 0.3:
                    time_distribution['moderate'] += 1
                else:
                    time_distribution['old'] += 1

            stats['sources'] = sources
            stats['score_distribution'] = score_distribution
            stats['time_distribution'] = time_distribution

            return stats

        except Exception as e:
            logger.error(f"Statistics generation failed: {e}")
            return {}

    def _format_search_statistics(self, stats: Dict[str, Any], response) -> str:
        """Format search statistics"""
        lines = []

        lines.append(f"📊 **Search Statistics**")
        lines.append("")

        # Basic stats
        lines.append(f"🔍 **Search Overview:**")
        lines.append(f"• Method: {stats.get('search_method', 'unknown')}")
        lines.append(f"• Candidates: {stats.get('total_candidates', 0)}")
        lines.append(f"• Returned: {stats.get('returned_results', 0)}")
        lines.append(f"• Response time: {stats.get('response_time_ms', 0)}ms")
        lines.append("")

        # Diversity metrics
        diversity = stats.get('diversity', {})
        if diversity:
            lines.append(f"🌈 **Diversity:**")
            lines.append(f"• Unique sources: {diversity.get('unique_domains', 0)}")
            lines.append(f"• Diversity score: {diversity.get('diversity_score', 0):.2f}")
            lines.append("")

        # Score distribution
        score_dist = stats.get('score_distribution', {})
        if score_dist:
            lines.append(f"⭐ **Quality Distribution:**")
            lines.append(f"• High (≥0.7): {score_dist.get('high', 0)}")
            lines.append(f"• Medium (≥0.4): {score_dist.get('medium', 0)}")
            lines.append(f"• Low (<0.4): {score_dist.get('low', 0)}")
            lines.append("")

        # Time distribution
        time_dist = stats.get('time_distribution', {})
        if time_dist:
            lines.append(f"⏰ **Freshness:**")
            lines.append(f"• Recent: {time_dist.get('recent', 0)}")
            lines.append(f"• Moderate: {time_dist.get('moderate', 0)}")
            lines.append(f"• Older: {time_dist.get('old', 0)}")
            lines.append("")

        # Top sources
        sources = stats.get('sources', {})
        if sources:
            lines.append(f"📰 **Top Sources:**")
            sorted_sources = sorted(sources.items(), key=lambda x: x[1], reverse=True)
            for domain, count in sorted_sources[:5]:
                lines.append(f"• {self._escape_markdown(domain)}: {count}")

        return "\n".join(lines)

    def _generate_related_queries(self, response) -> List[Dict[str, str]]:
        """Generate related query suggestions"""
        try:
            related = []

            if not response.results:
                return related

            # Extract topics from titles and content
            topics = set()
            entities = set()

            for result in response.results[:5]:
                title = result.get('title_norm', result.get('title', ''))
                text = result.get('text', result.get('clean_text', ''))

                # Simple topic extraction from titles
                title_words = [w for w in title.split() if len(w) > 4]
                topics.update(title_words[:3])

                # Extract potential entities (capitalized words)
                entities.update([w for w in text.split()[:50] if w.isupper() and len(w) > 2])

            # Generate related queries
            base_query = response.query_normalized

            # Topic-based expansions
            for topic in list(topics)[:3]:
                related.append({
                    'title': f"{topic.title()} Analysis",
                    'query': f"{base_query} {topic}"
                })

            # Entity-based expansions
            for entity in list(entities)[:2]:
                related.append({
                    'title': f"{entity} Context",
                    'query': f"{entity} {base_query}"
                })

            # Question variations
            if not base_query.startswith(('what', 'how', 'why')):
                related.append({
                    'title': "What is...",
                    'query': f"what is {base_query}"
                })

                related.append({
                    'title': "How does...",
                    'query': f"how does {base_query} work"
                })

            return related[:6]

        except Exception as e:
            logger.error(f"Related query generation failed: {e}")
            return []

    def _format_related_queries(self, queries: List[Dict[str, str]], original_query: str) -> str:
        """Format related queries"""
        lines = []

        lines.append(f"🔗 **Related Topics**")
        lines.append(f"Based on: `{self._escape_markdown(original_query)}`")
        lines.append("")

        lines.append(f"Click a topic below to explore:")

        return "\n".join(lines)

    def _generate_refinement_options(self, response) -> Dict[str, Any]:
        """Generate refinement options for search"""
        try:
            options = {
                'time_filters_available': True,
                'method_alternatives': [],
                'source_suggestions': [],
                'query_modifications': []
            }

            # Method alternatives
            current_method = response.search_method
            if current_method != 'semantic':
                options['method_alternatives'].append('semantic')
            if current_method != 'fts':
                options['method_alternatives'].append('fts')

            # Source suggestions (top domains from results)
            sources = {}
            for result in response.results:
                domain = result.get('source_domain', result.get('domain'))
                if domain:
                    sources[domain] = sources.get(domain, 0) + 1

            top_sources = sorted(sources.items(), key=lambda x: x[1], reverse=True)[:3]
            options['source_suggestions'] = [domain for domain, count in top_sources]

            return options

        except Exception as e:
            logger.error(f"Refinement options generation failed: {e}")
            return {}

    def _format_refinement_options(self, options: Dict[str, Any], query: str) -> str:
        """Format refinement options"""
        lines = []

        lines.append(f"🔧 **Refine Your Search**")
        lines.append(f"Current query: `{self._escape_markdown(query)}`")
        lines.append("")

        lines.append(f"Choose a refinement option:")
        lines.append(f"• **Time filters** - Focus on recent content")
        lines.append(f"• **Search method** - Change algorithm")
        lines.append(f"• **Sources** - Filter by domain")

        return "\n".join(lines)

    def _escape_markdown(self, text: str) -> str:
        """Escape markdown special characters"""
        if not text:
            return ""

        escape_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
        for char in escape_chars:
            text = text.replace(char, f'\\{char}')

        return text

    def _truncate_text(self, text: str, max_length: int) -> str:
        """Truncate text to maximum length"""
        if not text or len(text) <= max_length:
            return text

        return text[:max_length - 3] + "..."

    async def _send_message(self, chat_id: str, text: str, reply_markup: Dict = None) -> bool:
        """Send message to chat (placeholder - would use bot's send method)"""
        # This would call the actual bot's send message method
        logger.info(f"Would send to {chat_id}: {text[:100]}...")
        return True

    def cleanup_old_sessions(self, hours: int = 6):
        """Clean up old explanation sessions"""
        try:
            cutoff = datetime.utcnow() - timedelta(hours=hours)
            expired_sessions = []

            for session_id, data in self.explanation_sessions.items():
                if data.get('timestamp', cutoff) < cutoff:
                    expired_sessions.append(session_id)

            for session_id in expired_sessions:
                del self.explanation_sessions[session_id]

            if expired_sessions:
                logger.info(f"Cleaned up {len(expired_sessions)} expired explanation sessions")

        except Exception as e:
            logger.error(f"Session cleanup failed: {e}")