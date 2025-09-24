"""
Advanced Rate Limiter for Telegram Bots
Implements 2025 best practices for Telegram API rate limiting
"""

import asyncio
import logging
from collections import defaultdict
from time import time
from typing import Dict, List
import json

logger = logging.getLogger(__name__)

class TelegramRateLimiter:
    """
    Advanced rate limiter following Telegram's 2025 best practices

    Limits:
    - 30 messages per second globally
    - 20 messages per minute per chat/group
    - 1 message per second per private chat (recommended)
    """

    def __init__(self):
        self.chat_limits: Dict[str, List[float]] = defaultdict(list)
        self.global_limits: List[float] = []
        self.user_limits: Dict[str, List[float]] = defaultdict(list)

        # Rate limiting windows
        self.GLOBAL_WINDOW = 1.0  # 1 second for global limit
        self.CHAT_WINDOW = 60.0   # 1 minute for chat limit
        self.USER_WINDOW = 1.0    # 1 second for user limit

        # Limits
        self.GLOBAL_LIMIT = 30    # 30/second globally
        self.CHAT_LIMIT = 20      # 20/minute per chat
        self.USER_LIMIT = 1       # 1/second per user

        # Backoff settings
        self.MAX_RETRIES = 3
        self.BASE_DELAY = 1.0
        self.MAX_DELAY = 60.0

        logger.info("🚦 Rate limiter initialized with 2025 Telegram limits")

    def _cleanup_old_entries(self, entries: List[float], window: float) -> List[float]:
        """Remove entries older than the time window"""
        now = time()
        return [t for t in entries if now - t < window]

    async def check_global_limit(self) -> bool:
        """Check if we're within global rate limits (30/second)"""
        now = time()
        self.global_limits = self._cleanup_old_entries(self.global_limits, self.GLOBAL_WINDOW)

        if len(self.global_limits) >= self.GLOBAL_LIMIT:
            sleep_time = self.GLOBAL_WINDOW - (now - self.global_limits[0])
            if sleep_time > 0:
                logger.warning(f"⏰ Global rate limit hit, sleeping {sleep_time:.2f}s")
                await asyncio.sleep(sleep_time)
                return False

        self.global_limits.append(now)
        return True

    async def check_chat_limit(self, chat_id: str) -> bool:
        """Check if we're within per-chat rate limits (20/minute)"""
        now = time()
        self.chat_limits[chat_id] = self._cleanup_old_entries(
            self.chat_limits[chat_id], self.CHAT_WINDOW
        )

        if len(self.chat_limits[chat_id]) >= self.CHAT_LIMIT:
            sleep_time = self.CHAT_WINDOW - (now - self.chat_limits[chat_id][0])
            if sleep_time > 0:
                logger.warning(f"⏰ Chat {chat_id} rate limit hit, sleeping {sleep_time:.2f}s")
                await asyncio.sleep(min(sleep_time, 60))  # Max 60s wait
                return False

        self.chat_limits[chat_id].append(now)
        return True

    async def check_user_limit(self, user_id: str) -> bool:
        """Check if we're within per-user rate limits (1/second recommended)"""
        now = time()
        self.user_limits[user_id] = self._cleanup_old_entries(
            self.user_limits[user_id], self.USER_WINDOW
        )

        if len(self.user_limits[user_id]) >= self.USER_LIMIT:
            sleep_time = self.USER_WINDOW - (now - self.user_limits[user_id][-1])
            if sleep_time > 0:
                logger.debug(f"⏰ User {user_id} rate limit, sleeping {sleep_time:.2f}s")
                await asyncio.sleep(sleep_time)
                return False

        self.user_limits[user_id].append(now)
        return True

    async def acquire(self, chat_id: str, user_id: str = None) -> bool:
        """
        Acquire rate limit permission for sending message
        Returns True if allowed, False if should retry later
        """
        try:
            # Check all limits
            if not await self.check_global_limit():
                return False

            if not await self.check_chat_limit(chat_id):
                return False

            if user_id and not await self.check_user_limit(user_id):
                return False

            return True

        except Exception as e:
            logger.error(f"Rate limiter error: {e}")
            return True  # Allow on error to prevent bot freeze

    async def send_with_retry(self, send_func, *args, **kwargs):
        """
        Send message with exponential backoff retry on rate limit errors
        """
        last_exception = None

        for attempt in range(self.MAX_RETRIES):
            try:
                # Execute the send function
                result = await send_func(*args, **kwargs)

                # Success
                if attempt > 0:
                    logger.info(f"✅ Message sent after {attempt + 1} attempts")

                return result

            except Exception as e:
                last_exception = e
                error_str = str(e).lower()

                # Check if it's a rate limit error (429)
                if "429" in error_str or "too many requests" in error_str:
                    delay = min(self.BASE_DELAY * (2 ** attempt), self.MAX_DELAY)
                    logger.warning(f"🚫 Rate limit error (attempt {attempt + 1}), retrying in {delay}s")
                    await asyncio.sleep(delay)
                    continue
                else:
                    # Non-rate-limit error, don't retry
                    logger.error(f"❌ Non-retryable error: {e}")
                    raise e

        # All retries exhausted
        logger.error(f"💥 All {self.MAX_RETRIES} retry attempts failed")
        raise last_exception

    def get_stats(self) -> Dict:
        """Get current rate limiter statistics"""
        now = time()

        # Clean up for accurate stats
        self.global_limits = self._cleanup_old_entries(self.global_limits, self.GLOBAL_WINDOW)

        active_chats = 0
        active_users = 0

        for chat_id in list(self.chat_limits.keys()):
            self.chat_limits[chat_id] = self._cleanup_old_entries(
                self.chat_limits[chat_id], self.CHAT_WINDOW
            )
            if self.chat_limits[chat_id]:
                active_chats += 1

        for user_id in list(self.user_limits.keys()):
            self.user_limits[user_id] = self._cleanup_old_entries(
                self.user_limits[user_id], self.USER_WINDOW
            )
            if self.user_limits[user_id]:
                active_users += 1

        return {
            "global_requests_last_second": len(self.global_limits),
            "global_limit": self.GLOBAL_LIMIT,
            "active_chats": active_chats,
            "active_users": active_users,
            "total_tracked_chats": len(self.chat_limits),
            "total_tracked_users": len(self.user_limits),
            "limits": {
                "global": f"{self.GLOBAL_LIMIT}/second",
                "chat": f"{self.CHAT_LIMIT}/minute",
                "user": f"{self.USER_LIMIT}/second"
            }
        }

    def reset_limits(self, chat_id: str = None, user_id: str = None):
        """Reset rate limits for debugging/testing"""
        if chat_id:
            self.chat_limits[chat_id] = []
            logger.info(f"🔄 Reset rate limits for chat {chat_id}")

        if user_id:
            self.user_limits[user_id] = []
            logger.info(f"🔄 Reset rate limits for user {user_id}")

        if not chat_id and not user_id:
            self.global_limits = []
            self.chat_limits.clear()
            self.user_limits.clear()
            logger.info("🔄 Reset all rate limits")


# Global rate limiter instance
rate_limiter = TelegramRateLimiter()


# Decorator for rate-limited functions
def rate_limited(func):
    """Decorator to add rate limiting to message sending functions"""
    async def wrapper(*args, **kwargs):
        # Try to extract chat_id and user_id from arguments
        chat_id = None
        user_id = None

        # Common argument patterns
        if len(args) >= 2:
            chat_id = str(args[1])  # Usually second argument
        elif 'chat_id' in kwargs:
            chat_id = str(kwargs['chat_id'])

        if 'user_id' in kwargs:
            user_id = str(kwargs['user_id'])

        if chat_id:
            await rate_limiter.acquire(chat_id, user_id)

        return await rate_limiter.send_with_retry(func, *args, **kwargs)

    return wrapper


def main():
    """CLI for testing rate limiter"""
    import argparse

    parser = argparse.ArgumentParser(description='Telegram Rate Limiter Testing')
    parser.add_argument('command', choices=['stats', 'test', 'reset'])
    parser.add_argument('--chat-id', help='Chat ID for operations')
    parser.add_argument('--user-id', help='User ID for operations')

    args = parser.parse_args()

    if args.command == 'stats':
        stats = rate_limiter.get_stats()
        print("📊 Rate Limiter Statistics:")
        print(json.dumps(stats, indent=2))

    elif args.command == 'reset':
        rate_limiter.reset_limits(args.chat_id, args.user_id)
        print("✅ Rate limits reset")

    elif args.command == 'test':
        async def test_limits():
            print("🧪 Testing rate limits...")
            for i in range(5):
                allowed = await rate_limiter.acquire('test_chat', 'test_user')
                print(f"Request {i+1}: {'✅ Allowed' if allowed else '🚫 Rate limited'}")

        asyncio.run(test_limits())


if __name__ == "__main__":
    main()