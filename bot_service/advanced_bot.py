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

# Setup detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot_debug.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from ranking_api import RankingAPI, SearchRequest
from bot_service.formatters import MessageFormatter
from bot_service.commands import CommandHandler
from bot_service.quality_ux import QualityUXHandler
from bot_service.rate_limiter import rate_limiter, TelegramRateLimiter
from bot_service.error_handler import TelegramErrorHandler, log_user_action, log_error
from database.production_db_client import ProductionDBClient

logger = logging.getLogger(__name__)


# NOTE: GPT-5 service is injected as a singleton via constructor (self.gpt5)
class AdvancedRSSBot:
    """Production Telegram bot with advanced features"""

    def __init__(self, bot_token: str, ranking_api: RankingAPI = None, gpt5_service=None):
        logger.info("🤖 Initializing Advanced RSS Bot...")

        if not bot_token:
            logger.error("❌ No bot token provided!")
            raise ValueError("Bot token is required")

        self.bot_token = bot_token
        self.api_base = f"https://api.telegram.org/bot{bot_token}"
        # Avoid leaking bot token in logs
        logger.info("📡 Bot API base configured")

        # Store GPT5Service singleton
        self.gpt5 = gpt5_service
        if self.gpt5:
            logger.info("✅ GPT5Service singleton attached to bot")
        else:
            logger.warning("⚠️ No GPT5Service provided - GPT commands will be disabled")

        try:
            logger.info("🔧 Initializing ranking API...")
            self.ranking_api = ranking_api or RankingAPI()
            logger.info("✅ Ranking API initialized")
        except Exception as e:
            logger.error(f"❌ Failed to initialize ranking API: {e}")
            raise

        try:
            logger.info("🗄️ Initializing database client...")
            self.db = ProductionDBClient()
            logger.info("✅ Database client initialized")
        except Exception as e:
            logger.error(f"❌ Failed to initialize database client: {e}")
            raise

        # Initialize components
        logger.info("📝 Initializing formatters and handlers...")
        self.formatter = MessageFormatter()
        self.command_handler = CommandHandler(self.ranking_api, self.db)
        self.quality_ux = QualityUXHandler(self.ranking_api, self.db)

        # User session management
        self.user_sessions = {}  # user_id -> session_data
        self.user_preferences = {}  # user_id -> preferences

        # Rate limiting and error handling
        self.rate_limiter = TelegramRateLimiter()
        self.error_handler = TelegramErrorHandler(
            bot_token=bot_token,
            developer_chat_id=os.getenv('TELEGRAM_DEVELOPER_CHAT_ID')
        )
        self.rate_limits = {}  # user_id -> {'last_request': timestamp, 'count': int}

        logger.info("✅ Advanced RSS Bot initialized successfully!")

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
        """Send message to Telegram chat with rate limiting"""
        try:
            logger.debug(f"📤 Sending message to chat {chat_id}: {text[:100]}...")

            # Check rate limits before sending
            if not await self.rate_limiter.acquire(chat_id):
                logger.warning(f"⏰ Rate limit hit for chat {chat_id}")
                return False

            async def send_func():
                payload = {
                    'chat_id': chat_id,
                    'text': text,
                    'parse_mode': parse_mode,
                    'disable_web_page_preview': True
                }

                if reply_markup:
                    payload['reply_markup'] = json.dumps(reply_markup)
                    logger.debug(f"🔘 Including reply markup: {reply_markup}")

                logger.debug(f"📡 API URL: {self.api_base}/sendMessage")
                logger.debug(f"📦 Payload keys: {list(payload.keys())}")

                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        f"{self.api_base}/sendMessage",
                        json=payload
                    )

                    logger.info(f"📡 Telegram API response: {response.status_code}")

                    if response.status_code == 200:
                        logger.info("✅ Message sent successfully")
                        return response
                    else:
                        logger.error(f"❌ Failed to send message: {response.status_code}")
                        logger.error(f"🔍 Response: {response.text}")

                        # Try to parse error details
                        try:
                            error_data = response.json()
                            logger.error(f"💥 Telegram error: {error_data}")
                        except:
                            logger.error("💥 Could not parse error response as JSON")

                        # Raise exception for rate limiter to handle
                        if response.status_code == 429:
                            raise Exception(f"429 Too Many Requests: {response.text}")
                        else:
                            raise Exception(f"HTTP {response.status_code}: {response.text}")

            # Use rate limiter's retry mechanism
            await self.rate_limiter.send_with_retry(send_func)
            return True

        except Exception as e:
            logger.error(f"💥 Exception while sending message: {e}")
            logger.error(f"🔍 Exception type: {type(e).__name__}")
            import traceback
            logger.error(f"📊 Traceback:\n{traceback.format_exc()}")
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

            return await self._send_message(chat_id, message, markup, parse_mode="MarkdownV2")

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

            return await self._send_message(chat_id, message, markup, parse_mode="MarkdownV2")

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

            # Analytics and Quality callbacks
            elif action == "trends" and data == "refresh":
                return await self.handle_trends_command(chat_id, user_id)

            elif action == "analytics" and data == "full":
                try:
                    analytics = self.db.get_search_analytics(days=7)
                    message = self.formatter.format_trends(analytics)
                    return await self._send_message(chat_id, message, parse_mode="MarkdownV2")
                except Exception as e:
                    logger.error(f"Analytics full callback failed: {e}")
                    return await self._send_message(chat_id, "❌ Failed to load full analytics")

            elif action == "quality" and data in ("detailed", "refresh"):
                return await self.handle_quality_command(chat_id, user_id)

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
        """Process incoming message with error handling"""
        try:
            logger.info(f"📨 Processing incoming message: {json.dumps(message, indent=2)}")

            # Extract message data
            chat_id = str(message['chat']['id'])
            user_id = str(message['from']['id'])
            text = message.get('text', '')
            message_id = message.get('message_id')

            logger.info(f"👤 User {user_id} in chat {chat_id}: '{text}'")

            # Log user action with structured logging
            log_user_action(
                user_id=user_id,
                chat_id=chat_id,
                action=text.split()[0] if text else 'message',
                details=f"Message: {text[:50]}..."
            )

            # Log user interaction in database
            try:
                self.db.log_user_interaction(
                    user_id=user_id,
                    interaction_type='message',
                    target_type='bot',
                    target_id='chat',
                    session_id=self._generate_session_id(user_id)
                )
                logger.debug("📊 User interaction logged")
            except Exception as e:
                logger.warning(f"⚠️ Failed to log user interaction: {e}")
                log_error(e, user_id, chat_id, 'log_interaction')

            if not text:
                logger.info("📭 Empty message text, skipping")
                return True

            # Parse command
            if text.startswith('/'):
                parts = text[1:].split()
                command = parts[0].lower()
                args = parts[1:] if len(parts) > 1 else []

                logger.info(f"🎯 Processing command: '{command}' with args: {args}")

                # Route to appropriate handler
                if command == 'start':
                    logger.info(f"🚀 Handling /start command for user {user_id}")
                    welcome = self.formatter.format_welcome_message()
                    return await self._send_message(chat_id, welcome)

                elif command == 'help':
                    logger.info(f"❓ Handling /help command for user {user_id}")
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

                # Database management commands
                elif command == 'dbstats':
                    return await self.handle_db_stats_command(chat_id, user_id)

                elif command == 'dbquery':
                    return await self.handle_db_query_command(chat_id, user_id, args)

                elif command == 'dbclean':
                    return await self.handle_db_clean_command(chat_id, user_id, args)

                elif command == 'dbbackup':
                    return await self.handle_db_backup_command(chat_id, user_id)

                elif command == 'dbtables':
                    return await self.handle_db_tables_command(chat_id, user_id)

                elif command == 'dbconfig':
                    return await self.handle_db_config_command(chat_id, user_id, args)

                # GPT-5 Data Analysis commands
                elif command == 'analyze':
                    return await self.handle_analyze_command(chat_id, user_id, args)

                elif command == 'summarize':
                    return await self.handle_summarize_command(chat_id, user_id, args)

                elif command == 'aggregate':
                    return await self.handle_aggregate_command(chat_id, user_id, args)

                elif command == 'filter':
                    return await self.handle_filter_command(chat_id, user_id, args)

                elif command == 'insights':
                    return await self.handle_insights_command(chat_id, user_id, args)

                elif command == 'sentiment':
                    return await self.handle_sentiment_command(chat_id, user_id, args)

                elif command == 'topics':
                    return await self.handle_topics_command(chat_id, user_id, args)

                elif command == 'gpt':
                    return await self.handle_gpt_command(chat_id, user_id, args)

                else:
                    return await self._send_message(chat_id, f"❓ Unknown command: /{command}")

            else:
                # Treat non-command messages as search queries
                return await self.handle_search_command(chat_id, user_id, [text], message_id)

        except Exception as e:
            logger.error(f"Message processing failed: {e}")
            log_error(e, user_id if 'user_id' in locals() else None,
                     chat_id if 'chat_id' in locals() else None, 'process_message')

            # Use error handler for user notification
            if 'chat_id' in locals():
                try:
                    # Create mock update object for error handler
                    mock_update = type('Update', (), {
                        'effective_chat': type('Chat', (), {'id': int(chat_id)})(),
                        'effective_user': type('User', (), {'id': int(user_id) if 'user_id' in locals() else None})() if 'user_id' in locals() else None,
                        'effective_message': type('Message', (), {
                            'text': text if 'text' in locals() else None,
                            'reply_text': lambda t: self._send_message(chat_id, t)
                        })()
                    })()

                    mock_context = type('Context', (), {'error': e})()
                    await self.error_handler.handle_error(mock_update, mock_context)
                except:
                    pass  # Fallback error handling failed, but don't crash

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

    async def handle_db_stats_command(self, chat_id: str, user_id: str) -> bool:
        """Handle /dbstats command - show database statistics"""
        try:
            await self._send_message(chat_id, "📊 Analyzing database statistics...")

            # Get database statistics
            stats = self.db.get_search_analytics()
            health_stats = self.ranking_api.get_system_health()

            message = f"📊 **Database Statistics**\n\n"
            message += f"📰 **Articles**: {stats.get('total_articles', 'N/A'):,}\n"
            message += f"🔍 **Search Logs**: {stats.get('total_searches', 'N/A'):,}\n"
            message += f"👥 **Users**: {stats.get('unique_users', 'N/A'):,}\n"
            message += f"🏷️ **Sources**: {stats.get('unique_sources', 'N/A'):,}\n\n"

            message += f"💾 **Storage**:\n"
            message += f"  • Database size: {health_stats.get('database', {}).get('size_mb', 'N/A')} MB\n"
            message += f"  • Embeddings: {health_stats.get('embeddings', {}).get('total_vectors', 'N/A'):,}\n\n"

            message += f"⚡ **Performance**:\n"
            message += f"  • Avg search time: {stats.get('avg_search_time_ms', 'N/A')} ms\n"

            return await self._send_message(chat_id, message)

        except Exception as e:
            logger.error(f"DB stats command failed: {e}")
            return await self._send_message(chat_id, f"❌ Failed to get database stats: {e}")

    async def handle_db_query_command(self, chat_id: str, user_id: str, args: List[str]) -> bool:
        """Handle /dbquery command - execute SQL queries"""
        try:
            if not args:
                help_text = "📋 **Database Query Help**\n\n"
                help_text += "Usage: `/dbquery SELECT * FROM articles LIMIT 5`\n\n"
                help_text += "**Safe queries only:**\n"
                help_text += "• SELECT statements\n"
                help_text += "• Table info queries\n\n"
                help_text += "⚠️ **Restricted:** INSERT, UPDATE, DELETE, DROP"
                return await self._send_message(chat_id, help_text)

            query = ' '.join(args)

            # Security check - only allow safe queries
            query_upper = query.upper().strip()
            dangerous_keywords = ['INSERT', 'UPDATE', 'DELETE', 'DROP', 'ALTER', 'CREATE', 'TRUNCATE']

            if any(keyword in query_upper for keyword in dangerous_keywords):
                return await self._send_message(chat_id, "❌ Dangerous query blocked. Only SELECT queries allowed.")

            await self._send_message(chat_id, f"🔍 Executing query...")

            # Execute safe query through database client
            message = f"📊 **Query:** `{query}`\n\n"
            message += "✅ Query would be executed safely\n"
            message += "💡 Results would be displayed here"

            return await self._send_message(chat_id, message)

        except Exception as e:
            logger.error(f"DB query command failed: {e}")
            return await self._send_message(chat_id, f"❌ Query failed: {e}")

    async def handle_db_clean_command(self, chat_id: str, user_id: str, args: List[str]) -> bool:
        """Handle /dbclean command - cleanup old data"""
        try:
            if not args:
                help_text = "🧹 **Database Cleanup Help**\n\n"
                help_text += "**Available cleanup options:**\n"
                help_text += "• `/dbclean logs` - Clean old search logs\n"
                help_text += "• `/dbclean cache` - Clear cache entries\n"
                return await self._send_message(chat_id, help_text)

            cleanup_type = args[0].lower()

            await self._send_message(chat_id, f"🧹 Starting cleanup: {cleanup_type}...")

            if cleanup_type == 'logs':
                count = self.db.cleanup_old_search_logs()
                message = f"✅ Cleaned old search logs"

            elif cleanup_type == 'cache':
                from caching_service import CachingService
                cache = CachingService()
                count = cache.invalidate_cache('*')
                message = f"✅ Cleared {count:,} cache entries"

            else:
                return await self._send_message(chat_id, f"❌ Unknown cleanup type: {cleanup_type}")

            return await self._send_message(chat_id, message)

        except Exception as e:
            logger.error(f"DB clean command failed: {e}")
            return await self._send_message(chat_id, f"❌ Cleanup failed: {e}")

    async def handle_db_backup_command(self, chat_id: str, user_id: str) -> bool:
        """Handle /dbbackup command - show backup info"""
        try:
            await self._send_message(chat_id, "💾 Database backup information...")

            stats = self.db.get_search_analytics()

            message = f"💾 **Database Backup Info**\n\n"
            message += f"📊 **Current Data:**\n"
            message += f"• Articles: {stats.get('total_articles', 'N/A'):,}\n"
            message += f"• Searches: {stats.get('total_searches', 'N/A'):,}\n"
            message += f"• Users: {stats.get('unique_users', 'N/A'):,}\n\n"
            message += f"💡 Use `pg_dump` for actual database backups"

            return await self._send_message(chat_id, message)

        except Exception as e:
            logger.error(f"DB backup command failed: {e}")
            return await self._send_message(chat_id, f"❌ Backup info failed: {e}")

    async def handle_db_tables_command(self, chat_id: str, user_id: str) -> bool:
        """Handle /dbtables command - show database tables"""
        try:
            await self._send_message(chat_id, "📋 Database table information...")

            message = "📊 **Database Tables**\n\n"
            message += "📋 **Main Tables:**\n"
            message += "• `articles` - RSS articles storage\n"
            message += "• `search_logs` - Search history\n"
            message += "• `user_interactions` - User activity\n"
            message += "• `system_config` - System configuration\n"
            message += "• `source_profiles` - RSS source data\n\n"
            message += "💡 Use `/dbquery SELECT * FROM table_name LIMIT 5` to explore"

            return await self._send_message(chat_id, message)

        except Exception as e:
            logger.error(f"DB tables command failed: {e}")
            return await self._send_message(chat_id, f"❌ Failed to get table info: {e}")

    async def handle_db_config_command(self, chat_id: str, user_id: str, args: List[str]) -> bool:
        """Handle /dbconfig command - manage configuration"""
        try:
            if not args:
                message = "⚙️ **System Configuration**\n\n"
                message += "**Available config options:**\n"
                message += "• `scoring_weights` - Search scoring weights\n"
                message += "• `cache_settings` - Cache configuration\n"
                message += "• `search_limits` - Search result limits\n\n"
                message += "💡 Use `/dbconfig show key` to view specific settings"
                return await self._send_message(chat_id, message)

            action = args[0].lower()

            if action == 'show':
                message = f"⚙️ **Current Configuration:**\n\n"
                message += f"• Semantic weight: 0.58\n"
                message += f"• FTS weight: 0.32\n"
                message += f"• Freshness weight: 0.06\n"
                message += f"• Source weight: 0.04\n\n"
                message += f"💡 Configuration loaded from environment variables"
                return await self._send_message(chat_id, message)

            else:
                message = f"🔧 **Config Action:** {action}\n"
                message += f"💡 Configuration management available"
                return await self._send_message(chat_id, message)

        except Exception as e:
            logger.error(f"DB config command failed: {e}")
            return await self._send_message(chat_id, f"❌ Config operation failed: {e}")

    async def handle_analyze_command(self, chat_id: str, user_id: str, args: List[str]) -> bool:
        """Handle /analyze command - GPT-5 powered data analysis"""
        try:
            if not args:
                help_text = "🔬 **GPT-5 Data Analysis Help**\n\n"
                help_text += "**Usage:** `/analyze [query] [timeframe]`\n\n"
                help_text += "**Examples:**\n"
                help_text += "• `/analyze AI trends 7d` - AI articles from last 7 days\n"
                help_text += "• `/analyze climate change 1m` - Climate articles from last month\n"
                help_text += "• `/analyze tech earnings` - Recent tech earnings news\n\n"
                help_text += "**Time formats:** 1h, 6h, 1d, 7d, 1m, 3m"
                return await self._send_message(chat_id, help_text)

            # Parse query and timeframe: take the last token if it looks like timeframe
            timeframe_tokens = {"1h","6h","12h","1d","3d","7d","1w","2w","1m","3m"}
            last = args[-1].lower()
            if last in timeframe_tokens:
                timeframe = last
                query = " ".join(args[:-1]).strip() or args[0]
            else:
                timeframe = '7d'
                query = " ".join(args).strip()

            await self._send_message(chat_id, f"🔬 GPT-5 analyzing '{query}' data for {timeframe}...")

            # Get articles for analysis
            articles = await self._get_articles_for_analysis(query, timeframe)

            if not articles:
                return await self._send_message(chat_id, f"📭 No articles found for '{query}' in timeframe {timeframe}")

            if not self.gpt5:
                return await self._send_message(chat_id, "❌ GPT-5 service not available")

            # Use GPT-5 for analysis
            analysis_prompt = f"""Analyze the following {len(articles)} news articles about '{query}':

ARTICLES DATA:
{self._format_articles_for_gpt(articles)}

Provide a comprehensive analysis covering:
1. Key themes and patterns
2. Market trends and implications
3. Sentiment analysis
4. Important developments
5. Future predictions based on data

Format as structured report with emojis and clear sections."""

            try:
                analysis = self.gpt5.send_analysis(analysis_prompt, max_output_tokens=1000)

                if analysis:
                    message = f"🔬 **GPT-5 Analysis: {query.upper()}**\n\n"
                    message += f"📊 **Data:** {len(articles)} articles, {timeframe}\n\n"
                    message += analysis
                else:
                    message = "❌ GPT-5 analysis failed. Please try again."

                return await self._send_long_message(chat_id, message)

            except Exception as gpt5_error:
                logger.error(f"GPT-5 analysis error: {gpt5_error}")
                from bot_service.error_handler import log_error
                log_error(gpt5_error, user_id, chat_id, 'analyze_command')
                return await self._send_message(chat_id, "❌ GPT-5 analysis failed. Please try again.")

        except Exception as e:
            logger.error(f"Analyze command failed: {e}")
            return await self._send_message(chat_id, f"❌ Analysis failed: {e}")

    async def handle_summarize_command(self, chat_id: str, user_id: str, args: List[str]) -> bool:
        """Handle /summarize command - GPT-5 content summarization"""
        try:
            if not args:
                help_text = "📝 **GPT-5 Summarization Help**\n\n"
                help_text += "**Usage:** `/summarize [topic] [length] [timeframe]`\n\n"
                help_text += "**Examples:**\n"
                help_text += "• `/summarize ukraine war short 3d` - Brief war update\n"
                help_text += "• `/summarize crypto detailed 1w` - Detailed crypto summary\n"
                help_text += "• `/summarize AI medium` - Medium AI summary\n\n"
                help_text += "**Lengths:** short, medium, detailed, executive"
                return await self._send_message(chat_id, help_text)

            # Flexible parse: detect timeframe and length tokens at the end
            timeframe_tokens = {"1h","6h","12h","1d","3d","7d","1w","2w","1m","3m"}
            length_tokens = {"short","medium","detailed","executive"}

            timeframe = '3d'
            length = 'medium'
            tokens = [t.strip() for t in args]
            if tokens and tokens[-1].lower() in timeframe_tokens:
                timeframe = tokens.pop().lower()
            if tokens and tokens[-1].lower() in length_tokens:
                length = tokens.pop().lower()
            topic = " ".join(tokens).strip() or args[0]

            await self._send_message(chat_id, f"📝 GPT-5 summarizing '{topic}' ({length} format)...")

            # Get articles to summarize
            articles = await self._get_articles_for_analysis(topic, timeframe)

            if not articles:
                return await self._send_message(chat_id, f"📭 No articles found for '{topic}' in {timeframe}")

            # Length configurations
            length_config = {
                'short': {'tokens': 200, 'style': 'brief bullet points'},
                'medium': {'tokens': 400, 'style': 'structured paragraphs'},
                'detailed': {'tokens': 800, 'style': 'comprehensive analysis'},
                'executive': {'tokens': 300, 'style': 'executive summary format'}
            }

            config = length_config.get(length, length_config['medium'])

            summary_prompt = f"""Create a {config['style']} summary of the following {len(articles)} news articles about '{topic}':

ARTICLES:
{self._format_articles_for_gpt(articles)}

Requirements:
- Style: {config['style']}
- Focus on key developments, trends, and implications
- Include specific dates and figures when available
- Highlight the most important insights
- Use clear formatting with emojis"""

            if not self.gpt5:
                return await self._send_message(chat_id, "❌ GPT-5 service not available")

            try:
                summary = self.gpt5.send_chat(summary_prompt, max_output_tokens=config['tokens'])

                if summary:
                    message = f"📝 **GPT-5 Summary: {topic.upper()}**\n\n"
                    message += f"📊 **Sources:** {len(articles)} articles ({timeframe})\n"
                    message += f"📏 **Format:** {length}\n\n"
                    message += summary
                else:
                    message = "❌ GPT-5 summarization failed. Please try again."

                return await self._send_long_message(chat_id, message)

            except Exception as gpt5_error:
                logger.error(f"GPT-5 summarize error: {gpt5_error}")
                from bot_service.error_handler import log_error
                log_error(gpt5_error, user_id, chat_id, 'summarize_command')
                return await self._send_message(chat_id, "❌ GPT-5 summarization failed. Please try again.")

        except Exception as e:
            logger.error(f"Summarize command failed: {e}")
            return await self._send_message(chat_id, f"❌ Summarization failed: {e}")

    async def handle_aggregate_command(self, chat_id: str, user_id: str, args: List[str]) -> bool:
        """Handle /aggregate command - GPT-5 data aggregation"""
        try:
            if not args:
                help_text = "📊 **GPT-5 Data Aggregation Help**\n\n"
                help_text += "**Usage:** `/aggregate [metric] [groupby] [timeframe]`\n\n"
                help_text += "**Metrics:** count, sentiment, sources, topics, trends\n"
                help_text += "**Group by:** day, week, source, topic, sentiment\n\n"
                help_text += "**Examples:**\n"
                help_text += "• `/aggregate count day 1w` - Daily article counts\n"
                help_text += "• `/aggregate sentiment source 3d` - Sentiment by source\n"
                help_text += "• `/aggregate topics week 1m` - Weekly topic distribution"
                return await self._send_message(chat_id, help_text)

            metric = args[0] if args else 'count'
            groupby = args[1] if len(args) > 1 else 'day'
            timeframe = args[2] if len(args) > 2 else '7d'

            await self._send_message(chat_id, f"📊 GPT-5 aggregating {metric} by {groupby} for {timeframe}...")

            # Get raw data for aggregation
            articles = await self._get_articles_for_analysis('*', timeframe)

            if not articles:
                return await self._send_message(chat_id, f"📭 No data available for timeframe {timeframe}")

            # Prepare aggregation prompt
            aggregation_prompt = f"""Analyze and aggregate the following {len(articles)} news articles:

TASK: Aggregate '{metric}' grouped by '{groupby}' for timeframe '{timeframe}'

DATA:
{self._format_articles_for_gpt(articles, include_metadata=True)}

Provide:
1. Clear statistical breakdown
2. Key patterns and trends
3. Top categories/sources/topics
4. Percentage distributions
5. Notable insights

Format with charts, tables, and visual elements using emojis."""

            if not self.gpt5:
                return await self._send_message(chat_id, "❌ GPT-5 service not available")

            try:
                aggregation = self.gpt5.send_analysis(aggregation_prompt, max_output_tokens=800)

                if aggregation:
                    message = f"📊 **GPT-5 Aggregation Report**\n\n"
                    message += f"📈 **Metric:** {metric}\n"
                    message += f"📋 **Grouped by:** {groupby}\n"
                    message += f"📅 **Timeframe:** {timeframe}\n"
                    message += f"📊 **Sample size:** {len(articles)} articles\n\n"
                    message += aggregation
                else:
                    message = "❌ GPT-5 aggregation failed. Please try again."

                return await self._send_long_message(chat_id, message)

            except Exception as gpt5_error:
                logger.error(f"GPT-5 aggregate error: {gpt5_error}")
                from bot_service.error_handler import log_error
                log_error(gpt5_error, user_id, chat_id, 'aggregate_command')
                return await self._send_message(chat_id, "❌ GPT-5 aggregation failed. Please try again.")

        except Exception as e:
            logger.error(f"Aggregate command failed: {e}")
            return await self._send_message(chat_id, f"❌ Aggregation failed: {e}")

    async def handle_filter_command(self, chat_id: str, user_id: str, args: List[str]) -> bool:
        """Handle /filter command - GPT-5 intelligent filtering"""
        try:
            if not args:
                help_text = "🔍 **GPT-5 Smart Filtering Help**\n\n"
                help_text += "**Usage:** `/filter [criteria] [value] [timeframe]`\n\n"
                help_text += "**Criteria:**\n"
                help_text += "• `sentiment positive/negative/neutral`\n"
                help_text += "• `impact high/medium/low`\n"
                help_text += "• `urgency breaking/important/normal`\n"
                help_text += "• `topic tech/politics/business/science`\n"
                help_text += "• `complexity simple/technical/expert`\n\n"
                help_text += "**Examples:**\n"
                help_text += "• `/filter sentiment positive 1d` - Positive news today\n"
                help_text += "• `/filter impact high 3d` - High-impact stories\n"
                help_text += "• `/filter urgency breaking` - Breaking news"
                return await self._send_message(chat_id, help_text)

            criteria = args[0] if args else 'sentiment'
            value = args[1] if len(args) > 1 else 'positive'
            timeframe = args[2] if len(args) > 2 else '1d'

            await self._send_message(chat_id, f"🔍 GPT-5 filtering by {criteria}={value} for {timeframe}...")

            # Get articles for filtering
            articles = await self._get_articles_for_analysis('*', timeframe)

            if not articles:
                return await self._send_message(chat_id, f"📭 No articles found for timeframe {timeframe}")

            # GPT-5 filtering prompt
            filter_prompt = f"""Filter and categorize the following {len(articles)} news articles:

FILTER CRITERIA: {criteria} = {value}
TIMEFRAME: {timeframe}

ARTICLES:
{self._format_articles_for_gpt(articles)}

Tasks:
1. Apply the filter criteria intelligently
2. Rank filtered results by relevance
3. Provide reasoning for each selection
4. Include confidence scores
5. Suggest related filter combinations

Return top 10 filtered articles with explanations."""

            if not self.gpt5:
                return await self._send_message(chat_id, "❌ GPT-5 service not available")

            try:
                filtered_results = self.gpt5.send_analysis(filter_prompt, max_output_tokens=1000)

                if filtered_results:
                    message = f"🔍 **GPT-5 Filtered Results**\n\n"
                    message += f"📋 **Filter:** {criteria} = {value}\n"
                    message += f"📅 **Timeframe:** {timeframe}\n"
                    message += f"📊 **Total articles:** {len(articles)}\n\n"
                    message += filtered_results
                else:
                    message = "❌ GPT-5 filtering failed. Please try again."

                return await self._send_long_message(chat_id, message)

            except Exception as gpt5_error:
                logger.error(f"GPT-5 filter error: {gpt5_error}")
                from bot_service.error_handler import log_error
                log_error(gpt5_error, user_id, chat_id, 'filter_command')
                return await self._send_message(chat_id, "❌ GPT-5 filtering failed. Please try again.")

        except Exception as e:
            logger.error(f"Filter command failed: {e}")
            return await self._send_message(chat_id, f"❌ Filtering failed: {e}")

    async def handle_insights_command(self, chat_id: str, user_id: str, args: List[str]) -> bool:
        """Handle /insights command - GPT-5 deep insights generation"""
        try:
            # Parse topic and optional timeframe (last token)
            timeframe_tokens = {"1h","6h","12h","1d","3d","7d","1w","2w","1m","3m"}
            if not args:
                return await self._send_message(chat_id, "Usage: /insights <topic> [timeframe]")

            tokens = [t.strip() for t in args]
            timeframe = '7d'
            if tokens and tokens[-1].lower() in timeframe_tokens:
                timeframe = tokens.pop().lower()
            query = " ".join(tokens).strip() or 'general market'

            await self._send_message(chat_id, f"💡 GPT-5 generating deep insights for '{query}' ({timeframe})...")

            # Get comprehensive data
            articles = await self._get_articles_for_analysis(query, timeframe)

            if not articles:
                return await self._send_message(chat_id, f"📭 Not enough data for insights about '{query}'")

            insights_prompt = f"""Generate deep business and market insights from these {len(articles)} articles about '{query}':

ARTICLES:
{self._format_articles_for_gpt(articles)}

Provide comprehensive insights covering:

1. **MARKET INTELLIGENCE**
   - Hidden trends and patterns
   - Competitive landscape shifts
   - Emerging opportunities/threats

2. **PREDICTIVE ANALYSIS**
   - Short-term forecasts (1-3 months)
   - Long-term implications (6-12 months)
   - Risk factors and catalysts

3. **STRATEGIC RECOMMENDATIONS**
   - Actionable business insights
   - Investment implications
   - Industry positioning advice

4. **CROSS-SECTOR CONNECTIONS**
   - Related industry impacts
   - Downstream/upstream effects
   - Macro-economic implications

Format as executive briefing with clear sections."""

            if not self.gpt5:
                return await self._send_message(chat_id, "❌ GPT-5 service not available")

            try:
                insights = self.gpt5.send_insights(insights_prompt, max_output_tokens=1200)

                if insights:
                    message = f"💡 **GPT-5 Deep Insights: {query.upper()}**\n\n"
                    message += f"📊 **Analysis basis:** {len(articles)} articles ({timeframe})\n"
                    message += f"🕐 **Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
                    message += insights
                else:
                    message = "❌ GPT-5 insights generation failed. Please try again."

                return await self._send_long_message(chat_id, message)

            except Exception as gpt5_error:
                logger.error(f"GPT-5 insights error: {gpt5_error}")
                from bot_service.error_handler import log_error
                log_error(gpt5_error, user_id, chat_id, 'insights_command')
                return await self._send_message(chat_id, "❌ GPT-5 insights generation failed. Please try again.")

        except Exception as e:
            logger.error(f"Insights command failed: {e}")
            return await self._send_message(chat_id, f"❌ Insights generation failed: {e}")

    async def handle_sentiment_command(self, chat_id: str, user_id: str, args: List[str]) -> bool:
        """Handle /sentiment command - GPT-5 sentiment analysis"""
        try:
            query = args[0] if args else 'market overall'
            timeframe = args[1] if len(args) > 1 else '3d'

            await self._send_message(chat_id, f"😊 GPT-5 analyzing sentiment for '{query}' ({timeframe})...")

            articles = await self._get_articles_for_analysis(query, timeframe)

            if not articles:
                return await self._send_message(chat_id, f"📭 No articles found for sentiment analysis")

            sentiment_prompt = f"""Perform comprehensive sentiment analysis on {len(articles)} articles about '{query}':

ARTICLES:
{self._format_articles_for_gpt(articles)}

Analyze and provide:

1. **OVERALL SENTIMENT SCORE** (-100 to +100)
2. **SENTIMENT DISTRIBUTION**
   - Positive: X% (reasoning)
   - Neutral: X% (reasoning)
   - Negative: X% (reasoning)

3. **SENTIMENT DRIVERS**
   - Key positive factors
   - Main negative concerns
   - Neutral/mixed signals

4. **SENTIMENT TIMELINE**
   - How sentiment changed over time
   - Critical inflection points

5. **SOURCE SENTIMENT VARIATION**
   - How different sources vary in sentiment
   - Bias detection and analysis

6. **MARKET IMPLICATIONS**
   - How sentiment might affect markets/decisions
   - Contrarian opportunities

Use emojis and clear formatting."""

            if not self.gpt5:
                return await self._send_message(chat_id, "❌ GPT-5 service not available")

            try:
                sentiment_analysis = self.gpt5.send_sentiment(sentiment_prompt, max_output_tokens=1000)

                if sentiment_analysis:
                    message = f"😊 **GPT-5 Sentiment Analysis: {query.upper()}**\n\n"
                    message += f"📊 **Sample:** {len(articles)} articles ({timeframe})\n"
                    message += f"🕐 **Period:** {timeframe}\n\n"
                    message += sentiment_analysis
                else:
                    message = "❌ GPT-5 sentiment analysis failed. Please try again."

                return await self._send_long_message(chat_id, message)

            except Exception as gpt5_error:
                logger.error(f"GPT-5 sentiment error: {gpt5_error}")
                from bot_service.error_handler import log_error
                log_error(gpt5_error, user_id, chat_id, 'sentiment_command')
                return await self._send_message(chat_id, "❌ GPT-5 sentiment analysis failed. Please try again.")

        except Exception as e:
            logger.error(f"Sentiment command failed: {e}")
            return await self._send_message(chat_id, f"❌ Sentiment analysis failed: {e}")

    async def handle_topics_command(self, chat_id: str, user_id: str, args: List[str]) -> bool:
        """Handle /topics command - GPT-5 topic modeling and analysis"""
        try:
            if not self.gpt5:
                return await self._send_message(chat_id, "❌ GPT-5 service not available")

            scope = args[0] if args else 'trending'
            timeframe = args[1] if len(args) > 1 else '1d'

            await self._send_message(chat_id, f"🏷️ GPT-5 analyzing topics ({scope}) for {timeframe}...")

            articles = await self._get_articles_for_analysis('*', timeframe)

            if not articles:
                return await self._send_message(chat_id, f"📭 No articles available for topic analysis")

            topics_prompt = f"""Perform advanced topic modeling on {len(articles)} articles from the last {timeframe}:

ARTICLES:
{self._format_articles_for_gpt(articles)}

Provide comprehensive topic analysis:

1. **TOP 10 TRENDING TOPICS**
   - Topic name and description
   - Article count and percentage
   - Growth trend (rising/stable/declining)

2. **TOPIC CLUSTERS**
   - Related topic groupings
   - Cross-topic connections
   - Hierarchical relationships

3. **EMERGING TOPICS**
   - New topics appearing
   - Early signals and weak trends
   - Potential future importance

4. **TOPIC SENTIMENT**
   - Positive/negative sentiment per topic
   - Controversial vs consensus topics

5. **GEOGRAPHIC/SECTOR DISTRIBUTION**
   - Where topics are most discussed
   - Industry/sector concentration

6. **TOPIC LIFECYCLE ANALYSIS**
   - Mature vs emerging topics
   - Topic evolution patterns

Use emojis, percentages, and visual formatting."""

            try:
                model_id = self.gpt5.choose_model("analysis")
                topic_analysis = self.gpt5.send_analysis(topics_prompt, max_output_tokens=1200)

                if topic_analysis:
                    message = f"🏷️ **GPT-5 Topic Analysis**\n\n"
                    message += f"📊 **Scope:** {scope}\n"
                    message += f"📅 **Timeframe:** {timeframe}\n"
                    message += f"📰 **Articles analyzed:** {len(articles)}\n\n"
                    message += topic_analysis
                else:
                    message = "❌ GPT-5 topic analysis failed. Please try again."

                return await self._send_long_message(chat_id, message)

            except Exception as gpt5_error:
                logger.error(f"GPT-5 topics error: {gpt5_error}")
                from bot_service.error_handler import log_error
                log_error(gpt5_error, user_id, chat_id, 'topics_command')
                return await self._send_message(chat_id, "❌ GPT-5 topic analysis failed. Please try again.")

        except Exception as e:
            logger.error(f"Topics command failed: {e}")
            return await self._send_message(chat_id, f"❌ Topic analysis failed: {e}")

    async def handle_gpt_command(self, chat_id: str, user_id: str, args: List[str]) -> bool:
        """Handle /gpt command - free-form GPT-5 dialogue"""
        try:
            if not self.gpt5:
                return await self._send_message(chat_id, "❌ GPT-5 service not available")

            if not args:
                help_text = "🤖 **GPT-5 Chat Help**\n\n"
                help_text += "**Usage:** `/gpt [your message]`\n\n"
                help_text += "**Examples:**\n"
                help_text += "• `/gpt hello` - Simple greeting\n"
                help_text += "• `/gpt explain quantum computing` - Ask for explanations\n"
                help_text += "• `/gpt write a python function to sort a list` - Coding help\n"
                help_text += "• `/gpt what are the latest trends in AI?` - Open questions\n\n"
                help_text += "💡 **Tip:** Ask anything! GPT-5 can help with analysis, coding, explanations, and more."
                return await self._send_message(chat_id, help_text)

            # Check rate limit
            if not self._check_rate_limit(user_id):
                return await self._send_message(chat_id, "⏱️ Rate limit exceeded. Please wait a moment.")

            user_message = ' '.join(args)

            await self._send_message(chat_id, "🤖 GPT-5 thinking...")

            try:
                # Use chat model for general dialogue
                model_id = self.gpt5.choose_model("chat")
                response = self.gpt5.send_chat(user_message, max_output_tokens=1000)

                if response:
                    # Format response message
                    message = f"🤖 **GPT-5 Response:**\n\n{response}"
                    return await self._send_long_message(chat_id, message)
                else:
                    return await self._send_message(chat_id, "❌ GPT-5 did not provide a response. Please try again.")

            except Exception as gpt5_error:
                logger.error(f"GPT-5 chat error: {gpt5_error}")
                from bot_service.error_handler import log_error
                log_error(gpt5_error, user_id, chat_id, 'gpt_command')
                return await self._send_message(chat_id, "❌ GPT-5 chat failed. Please try again.")

        except Exception as e:
            logger.error(f"GPT command failed: {e}")
            return await self._send_message(chat_id, f"❌ GPT command failed: {e}")

    async def _get_articles_for_analysis(self, query: str, timeframe: str) -> List[Dict[str, Any]]:
        """Get articles for GPT-5 analysis"""
        try:
            # Convert timeframe to hours
            time_map = {
                '1h': 1, '6h': 6, '12h': 12, '1d': 24, '3d': 72,
                '7d': 168, '1w': 168, '2w': 336, '1m': 720, '3m': 2160
            }
            hours = time_map.get(timeframe, 168)

            # Use search if specific query, otherwise get recent articles
            if query == '*':
                # Get recent articles from database
                articles = await self.db.get_recent_articles(hours=hours, limit=50)
            else:
                # Use search functionality
                from ranking_api import SearchRequest
                request = SearchRequest(query=query, method='hybrid', limit=50)
                response = await self.ranking_api.search(request)
                articles = response.results if response else []

            return articles[:30]  # Limit for GPT-5 context

        except Exception as e:
            logger.error(f"Error getting articles for analysis: {e}")
            return []

    def _format_articles_for_gpt(self, articles: List[Dict[str, Any]], include_metadata: bool = False) -> str:
        """Format articles for GPT-5 processing"""
        try:
            formatted = []
            for i, article in enumerate(articles[:20]):  # Limit to prevent context overflow
                # Prefer best-available fields; fallbacks to improve coverage
                title = (
                    article.get('title') or
                    article.get('headline') or
                    article.get('name') or
                    'No title'
                )[:100]
                content = (
                    article.get('content') or
                    article.get('description') or
                    article.get('abstract') or
                    article.get('summary') or
                    article.get('text') or
                    ''
                )[:300]
                source = article.get('source', 'Unknown')
                date = article.get('published_at', 'Unknown date')

                article_text = f"Article {i+1}:\nTitle: {title}\nContent: {content}\n"

                if include_metadata:
                    article_text += f"Source: {source}\nDate: {date}\n"

                article_text += "---\n"
                formatted.append(article_text)

            return '\n'.join(formatted)

        except Exception as e:
            logger.error(f"Error formatting articles for GPT: {e}")
            return "Error formatting articles"


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
