"""
Advanced RSS News Telegram Bot
Production-ready bot with search, ask, trends, and user management
"""

import os
import sys
import asyncio
import logging
import json
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from ranking_api import RankingAPI, SearchRequest
from bot_service.formatters import MessageFormatter
from bot_service.commands import CommandHandler
from bot_service.quality_ux import QualityUXHandler
from database.production_db_client import ProductionDBClient

logger = logging.getLogger(__name__)


class AdvancedRSSBot:
    """Production Telegram bot with advanced features"""

    def __init__(self, bot_token: str, ranking_api: RankingAPI = None):
        self.bot_token = bot_token
        self.api_base = f"https://api.telegram.org/bot{bot_token}"
        self.ranking_api = ranking_api or RankingAPI()
        self.db = ProductionDBClient()

        # Initialize components
        self.formatter = MessageFormatter()
        self.command_handler = CommandHandler(self.ranking_api, self.db)
        self.quality_ux = QualityUXHandler(self.ranking_api, self.db)

        # User session management
        self.user_sessions = {}  # user_id -> session_data
        self.user_preferences = {}  # user_id -> preferences

        # Rate limiting
        self.rate_limits = {}  # user_id -> {'last_request': timestamp, 'count': int}

        logger.info("Advanced RSS Bot initialized")

    def _generate_session_id(self, user_id: str) -> str:
        """Generate unique session ID"""
        timestamp = datetime.utcnow().isoformat()
        return hashlib.md5(f"{user_id}_{timestamp}".encode()).hexdigest()[:16]

    def _check_rate_limit(self, user_id: str) -> bool:
        """Check if user is within rate limits"""
        now = datetime.utcnow()
        limit_window = 60  # seconds
        max_requests = 30  # per minute

        if user_id not in self.rate_limits:
            self.rate_limits[user_id] = {'last_request': now, 'count': 1}
            return True

        user_limit = self.rate_limits[user_id]
        time_diff = (now - user_limit['last_request']).total_seconds()

        if time_diff > limit_window:
            # Reset window
            self.rate_limits[user_id] = {'last_request': now, 'count': 1}
            return True

        if user_limit['count'] >= max_requests:
            return False

        user_limit['count'] += 1
        return True

    async def _send_message(self, chat_id: str, text: str,
                           reply_markup: Dict = None,
                           parse_mode: str = "Markdown") -> bool:
        """Send message to Telegram chat"""
        try:
            payload = {
                'chat_id': chat_id,
                'text': text,
                'parse_mode': parse_mode,
                'disable_web_page_preview': True
            }

            if reply_markup:
                payload['reply_markup'] = json.dumps(reply_markup)

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.api_base}/sendMessage",
                    json=payload
                )

                if response.status_code == 200:
                    return True
                else:
                    logger.error(f"Failed to send message: {response.status_code} - {response.text}")
                    return False

        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return False

    async def _send_long_message(self, chat_id: str, text: str,
                                reply_markup: Dict = None) -> bool:
        """Send long message, splitting if necessary"""
        max_length = 4000

        if len(text) <= max_length:
            return await self._send_message(chat_id, text, reply_markup)

        # Split message
        parts = []
        current_part = ""
        lines = text.split('\n')

        for line in lines:
            if len(current_part + line + '\n') > max_length:
                if current_part:
                    parts.append(current_part.strip())
                current_part = line + '\n'
            else:
                current_part += line + '\n'

        if current_part:
            parts.append(current_part.strip())

        # Send parts
        success_count = 0
        for i, part in enumerate(parts):
            if len(parts) > 1:
                part_header = f"📄 **Part {i+1}/{len(parts)}**\n\n"
                part = part_header + part

            # Only add markup to last part
            markup = reply_markup if i == len(parts) - 1 else None
            if await self._send_message(chat_id, part, markup):
                success_count += 1

        return success_count == len(parts)

    def _create_inline_keyboard(self, buttons: List[List[Dict[str, str]]]) -> Dict:
        """Create inline keyboard markup"""
        return {
            "inline_keyboard": buttons
        }

    async def handle_search_command(self, chat_id: str, user_id: str,
                                  args: List[str], message_id: int = None) -> bool:
        """Handle /search command"""
        try:
            if not args:
                help_text = self.formatter.format_search_help()
                return await self._send_message(chat_id, help_text)

            # Check rate limit
            if not self._check_rate_limit(user_id):
                return await self._send_message(chat_id, "⏱️ Rate limit exceeded. Please wait a moment.")

            query = ' '.join(args)
            session_id = self._generate_session_id(user_id)

            # Create search request
            search_request = SearchRequest(
                query=query,
                method='hybrid',
                limit=10,
                user_id=user_id,
                session_id=session_id,
                explain=True
            )

            # Perform search
            await self._send_message(chat_id, "🔍 Searching...")

            response = await self.ranking_api.search(search_request)

            if not response.results:
                no_results = self.formatter.format_no_results(query)
                return await self._send_message(chat_id, no_results)

            # Format results
            message = self.formatter.format_search_results(response)

            # Create action buttons
            buttons = [
                [
                    {"text": "🔍 Refine Search", "callback_data": f"refine:{session_id}"},
                    {"text": "💡 Explain Rankings", "callback_data": f"explain:{session_id}"}
                ],
                [
                    {"text": "📊 Show Stats", "callback_data": f"stats:{session_id}"},
                    {"text": "🔄 More Like This", "callback_data": f"similar:{session_id}"}
                ]
            ]

            markup = self._create_inline_keyboard(buttons)

            # Store session data
            self.user_sessions[session_id] = {
                'user_id': user_id,
                'chat_id': chat_id,
                'query': query,
                'response': response,
                'timestamp': datetime.utcnow()
            }

            return await self._send_long_message(chat_id, message, markup)

        except Exception as e:
            logger.error(f"Search command failed: {e}")
            return await self._send_message(chat_id, f"❌ Search failed: {e}")

    async def handle_ask_command(self, chat_id: str, user_id: str,
                               args: List[str]) -> bool:
        """Handle /ask command for RAG-style questions"""
        try:
            if not args:
                help_text = self.formatter.format_ask_help()
                return await self._send_message(chat_id, help_text)

            # Check rate limit
            if not self._check_rate_limit(user_id):
                return await self._send_message(chat_id, "⏱️ Rate limit exceeded. Please wait a moment.")

            question = ' '.join(args)

            await self._send_message(chat_id, "🤔 Analyzing question...")

            # Get context
            response = await self.ranking_api.ask(question, limit_context=5, user_id=user_id)

            if not response.get('context'):
                return await self._send_message(chat_id, "❌ No relevant information found to answer your question.")

            # Format response
            message = self.formatter.format_ask_response(response)

            # Create source buttons
            buttons = []
            if response.get('sources'):
                source_buttons = []
                for i, source in enumerate(response['sources'][:3]):
                    source_buttons.append({
                        "text": f"📰 {source['domain']}",
                        "url": source['url']
                    })
                    if len(source_buttons) == 2:  # 2 per row
                        buttons.append(source_buttons)
                        source_buttons = []

                if source_buttons:
                    buttons.append(source_buttons)

            # Add utility buttons
            buttons.append([
                {"text": "🔍 Related Search", "callback_data": f"related:{question}"},
                {"text": "📋 Full Sources", "callback_data": f"sources:{question}"}
            ])

            markup = self._create_inline_keyboard(buttons) if buttons else None

            return await self._send_long_message(chat_id, message, markup)

        except Exception as e:
            logger.error(f"Ask command failed: {e}")
            return await self._send_message(chat_id, f"❌ Question processing failed: {e}")

    async def handle_trends_command(self, chat_id: str, user_id: str) -> bool:
        """Handle /trends command"""
        try:
            await self._send_message(chat_id, "📈 Analyzing current trends...")

            # For now, use search analytics as trends
            analytics = self.db.get_search_analytics(days=1)

            message = self.formatter.format_trends(analytics)

            buttons = [
                [
                    {"text": "📊 Full Analytics", "callback_data": "analytics:full"},
                    {"text": "🔄 Refresh", "callback_data": "trends:refresh"}
                ]
            ]

            markup = self._create_inline_keyboard(buttons)

            return await self._send_message(chat_id, message, markup)

        except Exception as e:
            logger.error(f"Trends command failed: {e}")
            return await self._send_message(chat_id, f"❌ Trends analysis failed: {e}")

    async def handle_quality_command(self, chat_id: str, user_id: str) -> bool:
        """Handle /quality command"""
        try:
            health = self.ranking_api.get_system_health()
            message = self.formatter.format_system_health(health)

            buttons = [
                [
                    {"text": "📊 Detailed Metrics", "callback_data": "quality:detailed"},
                    {"text": "🔄 Refresh", "callback_data": "quality:refresh"}
                ]
            ]

            markup = self._create_inline_keyboard(buttons)

            return await self._send_message(chat_id, message, markup)

        except Exception as e:
            logger.error(f"Quality command failed: {e}")
            return await self._send_message(chat_id, f"❌ Quality check failed: {e}")

    async def handle_settings_command(self, chat_id: str, user_id: str) -> bool:
        """Handle /settings command"""
        try:
            # Get user preferences
            preferences = self.user_preferences.get(user_id, {
                'default_limit': 10,
                'search_method': 'hybrid',
                'show_explanations': True,
                'time_filter': None
            })

            message = self.formatter.format_user_settings(preferences)

            buttons = [
                [
                    {"text": "🔧 Search Method", "callback_data": "settings:method"},
                    {"text": "📊 Result Count", "callback_data": "settings:limit"}
                ],
                [
                    {"text": "💡 Explanations", "callback_data": "settings:explain"},
                    {"text": "⏰ Time Filter", "callback_data": "settings:time"}
                ],
                [
                    {"text": "🔄 Reset All", "callback_data": "settings:reset"}
                ]
            ]

            markup = self._create_inline_keyboard(buttons)

            return await self._send_message(chat_id, message, markup)

        except Exception as e:
            logger.error(f"Settings command failed: {e}")
            return await self._send_message(chat_id, f"❌ Settings failed: {e}")

    async def handle_callback_query(self, callback_data: str, chat_id: str,
                                  user_id: str, message_id: int) -> bool:
        """Handle inline button callbacks"""
        try:
            parts = callback_data.split(':', 1)
            if len(parts) != 2:
                return False

            action, data = parts

            if action == "explain":
                return await self.quality_ux.handle_explain_request(
                    chat_id, user_id, data, message_id
                )

            elif action == "stats":
                return await self.quality_ux.handle_stats_request(
                    chat_id, user_id, data, message_id
                )

            elif action == "similar":
                return await self.quality_ux.handle_similar_request(
                    chat_id, user_id, data, message_id
                )

            elif action == "refine":
                return await self.quality_ux.handle_refine_request(
                    chat_id, user_id, data, message_id
                )

            elif action.startswith("settings"):
                return await self._handle_settings_callback(
                    chat_id, user_id, action, data, message_id
                )

            else:
                return await self._send_message(chat_id, "❓ Unknown action")

        except Exception as e:
            logger.error(f"Callback query failed: {e}")
            return False

    async def _handle_settings_callback(self, chat_id: str, user_id: str,
                                      action: str, data: str, message_id: int) -> bool:
        """Handle settings-related callbacks"""
        # Implementation depends on specific settings being changed
        return await self._send_message(chat_id, "⚙️ Settings updated")

    async def process_message(self, message: Dict[str, Any]) -> bool:
        """Process incoming message"""
        try:
            # Extract message data
            chat_id = str(message['chat']['id'])
            user_id = str(message['from']['id'])
            text = message.get('text', '')
            message_id = message.get('message_id')

            # Log user interaction
            self.db.log_user_interaction(
                user_id=user_id,
                interaction_type='message',
                target_type='bot',
                target_id='chat',
                session_id=self._generate_session_id(user_id)
            )

            if not text:
                return True

            # Parse command
            if text.startswith('/'):
                parts = text[1:].split()
                command = parts[0].lower()
                args = parts[1:] if len(parts) > 1 else []

                # Route to appropriate handler
                if command == 'start':
                    welcome = self.formatter.format_welcome_message()
                    return await self._send_message(chat_id, welcome)

                elif command == 'help':
                    help_text = self.formatter.format_help_message()
                    return await self._send_message(chat_id, help_text)

                elif command == 'search':
                    return await self.handle_search_command(chat_id, user_id, args, message_id)

                elif command == 'ask':
                    return await self.handle_ask_command(chat_id, user_id, args)

                elif command == 'trends':
                    return await self.handle_trends_command(chat_id, user_id)

                elif command == 'quality':
                    return await self.handle_quality_command(chat_id, user_id)

                elif command == 'settings':
                    return await self.handle_settings_command(chat_id, user_id)

                else:
                    return await self._send_message(chat_id, f"❓ Unknown command: /{command}")

            else:
                # Treat non-command messages as search queries
                return await self.handle_search_command(chat_id, user_id, [text], message_id)

        except Exception as e:
            logger.error(f"Message processing failed: {e}")
            return False

    async def process_callback_query(self, callback_query: Dict[str, Any]) -> bool:
        """Process callback query from inline buttons"""
        try:
            callback_id = callback_query['id']
            callback_data = callback_query['data']
            message = callback_query['message']
            user = callback_query['from']

            chat_id = str(message['chat']['id'])
            user_id = str(user['id'])
            message_id = message['message_id']

            # Process callback
            success = await self.handle_callback_query(
                callback_data, chat_id, user_id, message_id
            )

            # Answer callback query
            await self._answer_callback_query(callback_id, "✅" if success else "❌")

            return success

        except Exception as e:
            logger.error(f"Callback query processing failed: {e}")
            return False

    async def _answer_callback_query(self, callback_query_id: str, text: str = None) -> bool:
        """Answer callback query"""
        try:
            payload = {'callback_query_id': callback_query_id}
            if text:
                payload['text'] = text

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.api_base}/answerCallbackQuery",
                    json=payload
                )
                return response.status_code == 200

        except Exception as e:
            logger.error(f"Failed to answer callback query: {e}")
            return False

    def cleanup_old_sessions(self, hours: int = 24):
        """Clean up old user sessions"""
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        expired_sessions = [
            session_id for session_id, data in self.user_sessions.items()
            if data.get('timestamp', cutoff) < cutoff
        ]

        for session_id in expired_sessions:
            del self.user_sessions[session_id]

        if expired_sessions:
            logger.info(f"Cleaned up {len(expired_sessions)} expired sessions")


async def main():
    """Test bot functionality"""
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')

    if not bot_token:
        print("Error: TELEGRAM_BOT_TOKEN environment variable not set")
        return

    # Initialize bot
    bot = AdvancedRSSBot(bot_token)

    # Test message
    test_message = {
        'chat': {'id': 123456789},
        'from': {'id': 123456789},
        'text': '/search artificial intelligence',
        'message_id': 1
    }

    success = await bot.process_message(test_message)
    print(f"Test message processed: {success}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())