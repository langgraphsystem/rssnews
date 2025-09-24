"""
Message Formatters for Telegram Bot
Handles formatting of search results, explanations, and UI elements
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)


class MessageFormatter:
    """Formats messages for Telegram bot"""

    def __init__(self):
        self.max_title_length = 80
        self.max_snippet_length = 200
        self.max_results_per_message = 8

    def _escape_markdown(self, text: str) -> str:
        """Escape markdown special characters"""
        if not text:
            return ""

        # Escape markdown v2 characters
        escape_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
        for char in escape_chars:
            text = text.replace(char, f'\\{char}')

        return text

    def _truncate_text(self, text: str, max_length: int) -> str:
        """Truncate text to maximum length"""
        if not text:
            return ""

        if len(text) <= max_length:
            return text

        return text[:max_length - 3] + "..."

    def _format_time_ago(self, published_at: str) -> str:
        """Format time difference in human-readable format"""
        if not published_at:
            return ""

        try:
            if isinstance(published_at, str):
                pub_date = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
            else:
                pub_date = published_at

            now = datetime.utcnow().replace(tzinfo=None)
            if pub_date.tzinfo:
                pub_date = pub_date.replace(tzinfo=None)

            diff = now - pub_date
            hours = diff.total_seconds() / 3600

            if hours < 1:
                return "Just now"
            elif hours < 24:
                return f"{int(hours)}h ago"
            elif hours < 168:  # 1 week
                return f"{int(hours/24)}d ago"
            else:
                return f"{int(hours/168)}w ago"

        except Exception as e:
            logger.warning(f"Error formatting time: {e}")
            return ""

    def format_welcome_message(self) -> str:
        """Format welcome message for new users"""
        return """🤖 **Welcome to RSS News Bot\\!**

I'm your intelligent news assistant powered by advanced search and AI analysis\\.

**🔍 Commands:**
• `/search [query]` \\- Search news articles
• `/ask [question]` \\- Get AI\\-powered answers
• `/trends` \\- Current trending topics
• `/quality` \\- System health metrics
• `/settings` \\- Configure preferences
• `/help` \\- Show detailed help

**💡 Quick Start:**
Just type `/search artificial intelligence` or ask me a question like `/ask what's happening with climate change?`

Ready to explore the news\\? 🚀"""

    def format_help_message(self) -> str:
        """Format detailed help message"""
        return """📖 **RSS News Bot Help**

**🔍 Search Commands:**
• `/search [query]` \\- Find relevant articles
• `/ask [question]` \\- Get contextual answers

**📊 Analytics:**
• `/trends` \\- Current trending topics
• `/quality` \\- System performance metrics

**🗄️ Database Management:**
• `/dbstats` \\- Database statistics
• `/dbquery [SQL]` \\- Execute safe queries
• `/dbclean [type]` \\- Clean old data
• `/dbbackup` \\- Backup information
• `/dbtables` \\- Show database tables
• `/dbconfig [key] [value]` \\- Manage configuration

**🤖 GPT\\-5 Data Analysis:**
• `/analyze [query] [timeframe]` \\- Deep data analysis
• `/summarize [topic] [length]` \\- AI\\-powered summaries
• `/aggregate [metric] [groupby]` \\- Data aggregation
• `/filter [criteria] [value]` \\- Smart filtering
• `/insights [topic]` \\- Business insights generation
• `/sentiment [query]` \\- Sentiment analysis
• `/topics [scope]` \\- Topic modeling & trends

**⚙️ Settings:**
• `/settings` \\- Configure search preferences
• Default: hybrid search, 10 results, explanations on

**🎯 Search Tips:**
• Use specific keywords: `AI regulation EU`
• Ask questions: `what is quantum computing?`
• Combine terms: `climate change renewable energy`

**🔘 Interactive Features:**
• Click buttons for explanations
• Refine searches with filters
• View source links directly

**📈 Advanced Features:**
• Semantic similarity search
• Real\\-time freshness scoring
• Duplicate detection
• Source authority ranking

Need help with a specific feature\\? Just ask\\! 💬"""

    def format_search_help(self) -> str:
        """Format search command help"""
        return """🔍 **Search Help**

**Usage:** `/search [your query]`

**Examples:**
• `/search artificial intelligence`
• `/search climate change policy`
• `/search tech earnings Q4`

**Search Types:**
• **Hybrid** \\(default\\): Combines keyword \\+ semantic search
• **Semantic**: AI\\-powered meaning\\-based search
• **Keyword**: Traditional text matching

Use `/settings` to change search preferences\\."""

    def format_ask_help(self) -> str:
        """Format ask command help"""
        return """🤔 **Ask Help**

**Usage:** `/ask [your question]`

**Examples:**
• `/ask what is artificial intelligence?`
• `/ask how does climate change affect economy?`
• `/ask latest developments in quantum computing`

I'll analyze relevant articles and provide contextual answers with source citations\\."""

    def format_no_results(self, query: str) -> str:
        """Format no results message"""
        return f"""🔍 **No Results Found**

Query: `{self._escape_markdown(query)}`

**Suggestions:**
• Try broader keywords
• Check spelling
• Use different terms
• Try `/ask` for question\\-based search

**Example:** Instead of "AAPL Q4 earnings", try "Apple quarterly earnings" """

    def format_search_results(self, response) -> str:
        """Format search results for display"""
        lines = []

        # Header
        lines.append(f"🔍 **Search Results**")
        lines.append(f"Query: `{self._escape_markdown(response.query)}`")
        lines.append(f"Found: {response.total_results} articles • Showing: {len(response.results)}")
        lines.append(f"Time: {response.response_time_ms}ms • Method: {response.search_method}")
        lines.append("")

        # Diversity info
        if response.diversity_metrics:
            diversity = response.diversity_metrics
            lines.append(f"📊 **Quality Metrics**")
            lines.append(f"• Unique sources: {diversity.get('unique_domains', 0)}")
            lines.append(f"• Diversity score: {diversity.get('diversity_score', 0):.2f}")
            lines.append("")

        # Results
        for i, result in enumerate(response.results[:self.max_results_per_message], 1):
            # Title and source
            title = self._truncate_text(
                result.get('title_norm', result.get('title', 'No title')),
                self.max_title_length
            )
            domain = result.get('source_domain', result.get('domain', result.get('source', 'Unknown')))
            time_ago = self._format_time_ago(result.get('published_at'))

            # Score info
            scores = result.get('scores', {})
            final_score = scores.get('final', 0)

            lines.append(f"**{i}\\. {self._escape_markdown(title)}**")
            lines.append(f"📰 {self._escape_markdown(domain)} • {time_ago} • Score: {final_score:.3f}")

            # Snippet
            text = result.get('text', result.get('clean_text', ''))
            if text:
                snippet = self._truncate_text(text, self.max_snippet_length)
                lines.append(f"💬 {self._escape_markdown(snippet)}")

            # URL
            url = result.get('url', '')
            if url:
                lines.append(f"🔗 [Read Full Article]({url})")

            lines.append("")

        # Footer
        if len(response.results) > self.max_results_per_message:
            remaining = len(response.results) - self.max_results_per_message
            lines.append(f"\\.\\.\\. and {remaining} more results")

        return "\n".join(lines)

    def format_ask_response(self, response: Dict[str, Any]) -> str:
        """Format ask/RAG response"""
        lines = []

        # Header
        lines.append(f"🤔 **Question Analysis**")
        lines.append(f"Q: `{self._escape_markdown(response['query'])}`")
        lines.append("")

        # Context summary
        context_count = response.get('total_context_articles', 0)
        response_time = response.get('response_time_ms', 0)
        lines.append(f"📚 **Context**: {context_count} articles analyzed in {response_time}ms")
        lines.append("")

        # Context snippets
        lines.append(f"📖 **Key Information:**")
        for i, snippet in enumerate(response.get('context', [])[:3], 1):
            title = self._truncate_text(snippet.get('title', ''), 60)
            domain = snippet.get('domain', 'Unknown')
            text = self._truncate_text(snippet.get('text', ''), 150)
            score = snippet.get('relevance_score', 0)

            lines.append(f"**{i}\\. {self._escape_markdown(title)}** \\({self._escape_markdown(domain)}\\)")
            lines.append(f"💬 {self._escape_markdown(text)}")
            lines.append(f"📊 Relevance: {score:.3f}")
            lines.append("")

        # Sources
        if response.get('sources'):
            lines.append(f"📰 **Sources:**")
            for source in response['sources'][:5]:
                domain = source.get('domain', 'Unknown')
                title = self._truncate_text(source.get('title', ''), 50)
                time_ago = self._format_time_ago(source.get('published_at'))

                lines.append(f"• {self._escape_markdown(domain)} \\- {self._escape_markdown(title)} \\({time_ago}\\)")

        return "\n".join(lines)

    def format_trends(self, analytics: Dict[str, Any]) -> str:
        """Format trending topics"""
        lines = []

        lines.append(f"📈 **Current Trends**")
        lines.append(f"Period: Last 24 hours")
        lines.append("")

        # Method stats
        method_stats = analytics.get('method_stats', [])
        if method_stats:
            lines.append(f"🔍 **Search Activity:**")
            for stat in method_stats:
                method = stat.get('method', 'unknown')
                total = stat.get('total', 0)
                users = stat.get('unique_users', 0)
                lines.append(f"• {method}: {total} searches \\({users} users\\)")
            lines.append("")

        # Top queries
        top_queries = analytics.get('top_queries', [])
        if top_queries:
            lines.append(f"🔥 **Trending Searches:**")
            for i, query_data in enumerate(top_queries[:10], 1):
                query = query_data.get('query', '')
                freq = query_data.get('frequency', 0)
                lines.append(f"{i}\\. `{self._escape_markdown(query)}` \\({freq}x\\)")
            lines.append("")

        # Performance
        performance = analytics.get('performance', {})
        if performance:
            avg_time = performance.get('avg_response_time_ms', 0)
            lines.append(f"⚡ **Performance:**")
            lines.append(f"• Average response: {avg_time}ms")
            lines.append(f"• System status: 🟢 Healthy")

        return "\n".join(lines)

    def format_system_health(self, health: Dict[str, Any]) -> str:
        """Format system health information"""
        lines = []

        lines.append(f"🏥 **System Health Report**")
        lines.append(f"Timestamp: {health.get('timestamp', 'Unknown')}")
        lines.append(f"Status: {health.get('system_status', 'Unknown')}")
        lines.append("")

        # Current weights
        weights = health.get('current_weights', {})
        if weights:
            lines.append(f"⚖️ **Scoring Weights:**")
            lines.append(f"• Semantic: {weights.get('semantic', 0):.2f}")
            lines.append(f"• Keywords: {weights.get('fts', 0):.2f}")
            lines.append(f"• Freshness: {weights.get('freshness', 0):.2f}")
            lines.append(f"• Source: {weights.get('source', 0):.2f}")
            lines.append("")

        # Analytics
        analytics = health.get('search_analytics', {})
        if analytics:
            method_stats = analytics.get('method_stats', [])
            total_searches = sum(stat.get('total', 0) for stat in method_stats)
            unique_users = sum(stat.get('unique_users', 0) for stat in method_stats)

            lines.append(f"📊 **Activity \\(24h\\):**")
            lines.append(f"• Total searches: {total_searches}")
            lines.append(f"• Unique users: {unique_users}")

            performance = analytics.get('performance', {})
            if performance:
                lines.append(f"• Avg response: {performance.get('avg_response_time_ms', 0)}ms")

        # Top domains
        top_domains = health.get('top_domains', [])
        if top_domains:
            lines.append("")
            lines.append(f"🏆 **Top Sources:**")
            for domain in top_domains[:5]:
                name = domain.get('domain', 'Unknown')
                score = domain.get('source_score', 0)
                lines.append(f"• {self._escape_markdown(name)}: {score:.2f}")

        return "\n".join(lines)

    def format_user_settings(self, preferences: Dict[str, Any]) -> str:
        """Format user settings"""
        lines = []

        lines.append(f"⚙️ **Your Settings**")
        lines.append("")

        lines.append(f"🔍 **Search Method:** {preferences.get('search_method', 'hybrid')}")
        lines.append(f"📊 **Default Results:** {preferences.get('default_limit', 10)}")
        lines.append(f"💡 **Show Explanations:** {'Yes' if preferences.get('show_explanations', True) else 'No'}")

        time_filter = preferences.get('time_filter')
        lines.append(f"⏰ **Time Filter:** {time_filter or 'None'}")

        lines.append("")
        lines.append(f"Use buttons below to change settings\\.")

        return "\n".join(lines)

    def format_explanation(self, explanation: Dict[str, Any]) -> str:
        """Format ranking explanation"""
        lines = []

        lines.append(f"💡 **Why This Result\\?**")
        lines.append("")

        # Score breakdown
        scores = explanation.get('score_breakdown', {})
        if scores:
            final = scores.get('final_score', 0)
            lines.append(f"📊 **Overall Score: {final:.3f}**")
            lines.append("")

            lines.append(f"**Components:**")
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
            lines.append(f"**Why Relevant:**")
            for reason in why_relevant[:3]:
                lines.append(f"• {self._escape_markdown(reason)}")
            lines.append("")

        # Query matches
        matches = explanation.get('query_matches', [])
        if matches:
            lines.append(f"**Query Matches:**")
            for match in matches[:2]:
                context = self._truncate_text(match.get('context', ''), 50)
                lines.append(f"• '{match.get('exact_match', '')}' in: {self._escape_markdown(context)}")
            lines.append("")

        # Source and timing
        if explanation.get('source_reason'):
            lines.append(f"**Source:** {self._escape_markdown(explanation['source_reason'])}")

        if explanation.get('freshness_reason'):
            lines.append(f"**Timing:** {self._escape_markdown(explanation['freshness_reason'])}")

        # Penalties
        penalties = explanation.get('penalties_applied', [])
        if penalties:
            lines.append("")
            lines.append(f"**Adjustments:**")
            for penalty in penalties:
                lines.append(f"• {self._escape_markdown(penalty)}")

        return "\n".join(lines)