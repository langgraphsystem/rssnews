"""
Advanced Error Handler for Telegram Bots
Implements 2025 best practices for error handling and logging
"""

import logging
import json
import traceback
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional
import httpx

logger = logging.getLogger(__name__)


class JsonFormatter(logging.Formatter):
    """JSON formatter for structured logging"""

    def format(self, record):
        log_entry = {
            'timestamp': self.formatTime(record),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'user_id': getattr(record, 'user_id', None),
            'chat_id': getattr(record, 'chat_id', None),
            'command': getattr(record, 'command', None),
            'error_type': getattr(record, 'error_type', None),
            'traceback': getattr(record, 'traceback', None)
        }

        # Remove None values
        return json.dumps({k: v for k, v in log_entry.items() if v is not None})


class TelegramErrorHandler:
    """
    Advanced error handler with developer notifications,
    user feedback, and structured logging
    """

    def __init__(self, bot_token: str, developer_chat_id: str = None):
        self.bot_token = bot_token
        self.developer_chat_id = developer_chat_id
        self.api_base = f"https://api.telegram.org/bot{bot_token}"

        # Error statistics
        self.error_count = 0
        self.error_types = {}
        self.last_errors = []

        # Setup structured logging
        self.setup_logging()

        logger.info("🚨 Advanced error handler initialized")

    def setup_logging(self):
        """Setup structured JSON logging"""
        # Create JSON formatter
        json_formatter = JsonFormatter()

        # File handler for errors
        error_handler = logging.FileHandler('bot_errors.log')
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(json_formatter)

        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(json_formatter)

        # Add to root logger
        root_logger = logging.getLogger()
        root_logger.addHandler(error_handler)
        root_logger.addHandler(console_handler)
        root_logger.setLevel(logging.INFO)

    async def handle_error(self, update: Any, context: Any, custom_message: str = None):
        """
        Global error handler for telegram bot

        Args:
            update: Telegram update object
            context: Bot context with error information
            custom_message: Custom error message for user
        """
        try:
            error = context.error
            self.error_count += 1

            # Extract context information
            chat_id = None
            user_id = None
            message_text = None
            command = None

            if update:
                if hasattr(update, 'effective_chat') and update.effective_chat:
                    chat_id = update.effective_chat.id

                if hasattr(update, 'effective_user') and update.effective_user:
                    user_id = update.effective_user.id

                if hasattr(update, 'effective_message') and update.effective_message:
                    message_text = update.effective_message.text

                    # Extract command if it's a command
                    if message_text and message_text.startswith('/'):
                        command = message_text.split()[0]

            # Error classification
            error_type = type(error).__name__
            error_msg = str(error)

            # Update error statistics
            self.error_types[error_type] = self.error_types.get(error_type, 0) + 1

            # Store recent error
            error_record = {
                'timestamp': datetime.now().isoformat(),
                'error_type': error_type,
                'error_message': error_msg,
                'chat_id': chat_id,
                'user_id': user_id,
                'command': command,
                'message_text': message_text
            }

            self.last_errors.append(error_record)
            if len(self.last_errors) > 50:  # Keep last 50 errors
                self.last_errors.pop(0)

            # Structured logging
            logger.error(
                f"Bot error: {error_type}: {error_msg}",
                extra={
                    'user_id': user_id,
                    'chat_id': chat_id,
                    'command': command,
                    'error_type': error_type,
                    'traceback': traceback.format_exc()
                }
            )

            # Notify developer
            await self.notify_developer(error_record, traceback.format_exc())

            # Send user-friendly message
            await self.notify_user(update, context, custom_message, error_type)

        except Exception as e:
            # Error in error handler - log but don't crash
            logger.critical(f"💥 Error in error handler: {e}")

    async def notify_developer(self, error_record: Dict, tb: str):
        """Send error notification to developer"""
        if not self.developer_chat_id:
            return

        try:
            # Create developer notification
            msg = f"🚨 **Bot Error Alert**\n\n"
            msg += f"**Type:** `{error_record['error_type']}`\n"
            msg += f"**Time:** {error_record['timestamp']}\n"

            if error_record['user_id']:
                msg += f"**User:** {error_record['user_id']}\n"

            if error_record['chat_id']:
                msg += f"**Chat:** {error_record['chat_id']}\n"

            if error_record['command']:
                msg += f"**Command:** `{error_record['command']}`\n"

            msg += f"**Message:** {error_record['error_message'][:500]}...\n\n"
            msg += f"**Traceback:**\n```\n{tb[:1000]}...\n```"

            # Send to developer
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(
                    f"{self.api_base}/sendMessage",
                    json={
                        'chat_id': self.developer_chat_id,
                        'text': msg,
                        'parse_mode': 'Markdown'
                    }
                )

        except Exception as e:
            logger.error(f"Failed to notify developer: {e}")

    async def notify_user(self, update: Any, context: Any,
                         custom_message: str = None, error_type: str = None):
        """Send user-friendly error message"""
        if not update or not hasattr(update, 'effective_message'):
            return

        try:
            # Default user-friendly messages based on error type
            if custom_message:
                user_msg = custom_message
            elif error_type == 'NetworkError':
                user_msg = "🌐 Проблемы с сетью. Попробуйте через минуту."
            elif error_type == 'TimedOut':
                user_msg = "⏰ Запрос занял слишком много времени. Попробуйте еще раз."
            elif error_type == 'BadRequest':
                user_msg = "❌ Неверный запрос. Проверьте команду и попробуйте снова."
            elif error_type == 'Unauthorized':
                user_msg = "🚫 Проблемы с авторизацией. Перезапустите бота с /start"
            elif error_type == 'RetryAfter':
                user_msg = "🚦 Слишком много запросов. Подождите немного."
            else:
                user_msg = "😔 Произошла ошибка. Мы уже работаем над исправлением!"

            # Add helpful tips
            user_msg += f"\n\n💡 Попробуйте:\n"
            user_msg += f"• /help - посмотреть доступные команды\n"
            user_msg += f"• /start - перезапустить бота\n"
            user_msg += f"• Подождать минуту и повторить"

            await update.effective_message.reply_text(user_msg)

        except Exception as e:
            logger.error(f"Failed to notify user: {e}")

    def get_error_stats(self) -> Dict[str, Any]:
        """Get error statistics"""
        return {
            'total_errors': self.error_count,
            'error_types': self.error_types,
            'top_errors': sorted(
                self.error_types.items(),
                key=lambda x: x[1],
                reverse=True
            )[:5],
            'recent_errors': self.last_errors[-10:] if self.last_errors else [],
            'error_rate': f"{len(self.last_errors)}/hour" if self.last_errors else "0/hour"
        }

    async def health_check(self) -> Dict[str, Any]:
        """Health check for monitoring systems"""
        try:
            # Test bot connection
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.api_base}/getMe")

            bot_status = "healthy" if response.status_code == 200 else "unhealthy"

            # Recent error analysis
            recent_errors = len([
                e for e in self.last_errors
                if (datetime.now() - datetime.fromisoformat(e['timestamp'])).seconds < 300
            ])

            error_status = "healthy" if recent_errors < 5 else "degraded" if recent_errors < 10 else "critical"

            return {
                'timestamp': datetime.now().isoformat(),
                'bot_status': bot_status,
                'error_status': error_status,
                'recent_errors_5min': recent_errors,
                'total_errors': self.error_count,
                'uptime_status': 'running'
            }

        except Exception as e:
            return {
                'timestamp': datetime.now().isoformat(),
                'bot_status': 'error',
                'error_status': 'critical',
                'error_message': str(e),
                'uptime_status': 'failing'
            }

    def reset_stats(self):
        """Reset error statistics"""
        self.error_count = 0
        self.error_types.clear()
        self.last_errors.clear()
        logger.info("🔄 Error statistics reset")


# Utility functions for logging with context
def log_with_context(level: str, message: str, **context):
    """Log message with additional context"""
    extra = {k: v for k, v in context.items() if v is not None}
    getattr(logger, level.lower())(message, extra=extra)


def log_user_action(user_id: str, chat_id: str, action: str, details: str = None):
    """Log user action with context"""
    log_with_context(
        'info',
        f"User action: {action}",
        user_id=user_id,
        chat_id=chat_id,
        command=action,
        details=details
    )


def log_error(error: Exception, user_id: str = None, chat_id: str = None, command: str = None):
    """Log error with context"""
    log_with_context(
        'error',
        f"Error: {str(error)}",
        user_id=user_id,
        chat_id=chat_id,
        command=command,
        error_type=type(error).__name__,
        traceback=traceback.format_exc()
    )


def main():
    """CLI for testing error handler"""
    import argparse

    parser = argparse.ArgumentParser(description='Error Handler Testing')
    parser.add_argument('command', choices=['stats', 'health', 'test'])
    parser.add_argument('--token', help='Bot token')
    parser.add_argument('--dev-chat', help='Developer chat ID')

    args = parser.parse_args()

    if not args.token:
        print("❌ Bot token required")
        return

    handler = TelegramErrorHandler(args.token, args.dev_chat)

    if args.command == 'stats':
        stats = handler.get_error_stats()
        print("📊 Error Statistics:")
        print(json.dumps(stats, indent=2))

    elif args.command == 'health':
        async def check_health():
            health = await handler.health_check()
            print("🏥 Health Check:")
            print(json.dumps(health, indent=2))

        asyncio.run(check_health())

    elif args.command == 'test':
        print("🧪 Testing error logging...")
        log_user_action('123', '456', '/test', 'Testing error handler')
        log_error(Exception("Test error"), '123', '456', '/test')
        print("✅ Test completed, check logs")


if __name__ == "__main__":
    main()