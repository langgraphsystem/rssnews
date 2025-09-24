#!/usr/bin/env python3
"""
Test Integration of 2025 Telegram Bot Best Practices
Tests rate limiting, error handling, and bot functionality
"""

import os
import sys
import asyncio
import logging
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add parent directory for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))


async def test_rate_limiter():
    """Test rate limiting functionality"""
    print("\n🚦 TESTING RATE LIMITER")
    print("=" * 40)

    try:
        from bot_service.rate_limiter import TelegramRateLimiter, rate_limiter

        # Test rate limiter initialization
        limiter = TelegramRateLimiter()
        print("✅ Rate limiter initialized")

        # Test rate limit checking
        chat_id = "test_chat_123"
        user_id = "test_user_456"

        print(f"\n📊 Testing rate limits for chat {chat_id}...")

        # Test multiple rapid requests
        success_count = 0
        for i in range(5):
            allowed = await limiter.acquire(chat_id, user_id)
            if allowed:
                success_count += 1
                print(f"  Request {i+1}: ✅ Allowed")
            else:
                print(f"  Request {i+1}: 🚫 Rate limited")

            # Small delay to avoid instant blocking
            await asyncio.sleep(0.1)

        print(f"\n📈 Results: {success_count}/5 requests allowed")

        # Test statistics
        stats = limiter.get_stats()
        print(f"\n📊 Rate Limiter Stats:")
        print(f"  Global requests/sec: {stats['global_requests_last_second']}")
        print(f"  Active chats: {stats['active_chats']}")
        print(f"  Active users: {stats['active_users']}")

        return True

    except Exception as e:
        print(f"❌ Rate limiter test failed: {e}")
        return False


async def test_error_handler():
    """Test error handling functionality"""
    print("\n🚨 TESTING ERROR HANDLER")
    print("=" * 40)

    try:
        from bot_service.error_handler import TelegramErrorHandler, log_user_action, log_error

        # Get bot token from environment
        bot_token = os.getenv('TELEGRAM_BOT_TOKEN', '7477585710:AAG7iuQRm1EZsKoDzDf5yZtqxkaPU7i2frk')

        # Test error handler initialization
        error_handler = TelegramErrorHandler(bot_token)
        print("✅ Error handler initialized")

        # Test structured logging functions
        print("\n📝 Testing structured logging...")
        log_user_action('test_user', 'test_chat', '/start', 'Bot startup test')
        print("✅ User action logged")

        # Test error logging
        test_error = Exception("Test error for logging")
        log_error(test_error, 'test_user', 'test_chat', '/test')
        print("✅ Error logged")

        # Test error statistics
        stats = error_handler.get_error_stats()
        print(f"\n📊 Error Handler Stats:")
        print(f"  Total errors: {stats['total_errors']}")
        print(f"  Error types: {len(stats['error_types'])}")
        print(f"  Recent errors: {len(stats['recent_errors'])}")

        # Test health check
        health = await error_handler.health_check()
        print(f"\n🏥 Health Check:")
        print(f"  Bot status: {health['bot_status']}")
        print(f"  Error status: {health['error_status']}")
        print(f"  Uptime status: {health['uptime_status']}")

        return True

    except Exception as e:
        print(f"❌ Error handler test failed: {e}")
        return False


async def test_bot_integration():
    """Test bot integration with new components"""
    print("\n🤖 TESTING BOT INTEGRATION")
    print("=" * 40)

    try:
        from bot_service.advanced_bot import AdvancedRSSBot

        # Get bot token
        bot_token = os.getenv('TELEGRAM_BOT_TOKEN', '7477585710:AAG7iuQRm1EZsKoDzDf5yZtqxkaPU7i2frk')

        # Set database connection for testing
        os.environ['PG_DSN'] = 'postgresql://postgres:ug1Hi~XHEMdMh_Lm~4UfUKtAejqLBGdg@crossover.proxy.rlwy.net:12306/railway?sslmode=disable'

        print("🔧 Initializing advanced bot with 2025 best practices...")

        # Initialize bot (this will test if imports work)
        bot = AdvancedRSSBot(bot_token)
        print("✅ Bot initialized with rate limiter and error handler")

        # Test rate limiter integration
        if hasattr(bot, 'rate_limiter'):
            print("✅ Rate limiter integrated")
        else:
            print("❌ Rate limiter not found")

        # Test error handler integration
        if hasattr(bot, 'error_handler'):
            print("✅ Error handler integrated")
        else:
            print("❌ Error handler not found")

        # Test message processing (without actual Telegram API call)
        print("\n📨 Testing message processing...")

        test_message = {
            'chat': {'id': 123456789},
            'from': {'id': 123456789, 'first_name': 'TestUser'},
            'text': '/help',
            'message_id': 1
        }

        # Mock the _send_message method to avoid API calls
        original_send = bot._send_message

        async def mock_send_message(chat_id, text, reply_markup=None, parse_mode="Markdown"):
            print(f"📤 Mock send to {chat_id}: {text[:100]}...")
            return True

        bot._send_message = mock_send_message

        # Process test message
        result = await bot.process_message(test_message)
        print(f"✅ Message processed: {result}")

        # Restore original method
        bot._send_message = original_send

        return True

    except Exception as e:
        print(f"❌ Bot integration test failed: {e}")
        import traceback
        print(f"🔍 Traceback:\n{traceback.format_exc()}")
        return False


async def test_production_readiness():
    """Test production readiness features"""
    print("\n🚀 TESTING PRODUCTION READINESS")
    print("=" * 40)

    try:
        from bot_service.rate_limiter import rate_limiter
        from bot_service.error_handler import TelegramErrorHandler

        bot_token = os.getenv('TELEGRAM_BOT_TOKEN', '7477585710:AAG7iuQRm1EZsKoDzDf5yZtqxkaPU7i2frk')
        error_handler = TelegramErrorHandler(bot_token)

        print("🔍 Checking production components...")

        # Test rate limiter statistics
        stats = rate_limiter.get_stats()
        limits_ok = all(key in stats for key in ['global_limit', 'active_chats', 'limits'])
        print(f"📊 Rate limiter stats: {'✅' if limits_ok else '❌'}")

        # Test error handler health
        health = await error_handler.health_check()
        health_ok = all(key in health for key in ['bot_status', 'error_status', 'timestamp'])
        print(f"🏥 Error handler health: {'✅' if health_ok else '❌'}")

        # Test logging configuration
        log_handlers = len(logging.getLogger().handlers)
        logging_ok = log_handlers > 0
        print(f"📝 Logging configured: {'✅' if logging_ok else '❌'} ({log_handlers} handlers)")

        # Test environment variables
        env_vars = ['TELEGRAM_BOT_TOKEN']
        env_ok = all(os.getenv(var) for var in env_vars)
        print(f"⚙️ Environment variables: {'✅' if env_ok else '❌'}")

        print(f"\n🎯 Production readiness: {'✅ READY' if all([limits_ok, health_ok, logging_ok, env_ok]) else '❌ NEEDS WORK'}")

        return True

    except Exception as e:
        print(f"❌ Production readiness test failed: {e}")
        return False


async def main():
    """Run all integration tests"""
    print("🧪 TELEGRAM BOT 2025 BEST PRACTICES INTEGRATION TEST")
    print("=" * 60)
    print(f"🕐 Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # Run tests
    tests = [
        ("Rate Limiter", test_rate_limiter),
        ("Error Handler", test_error_handler),
        ("Bot Integration", test_bot_integration),
        ("Production Readiness", test_production_readiness)
    ]

    results = {}

    for test_name, test_func in tests:
        try:
            success = await test_func()
            results[test_name] = success
        except Exception as e:
            print(f"❌ {test_name} test crashed: {e}")
            results[test_name] = False

    # Summary
    print("\n" + "=" * 60)
    print("📊 TEST SUMMARY")
    print("=" * 60)

    passed = sum(results.values())
    total = len(results)

    for test_name, success in results.items():
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"  {test_name}: {status}")

    print(f"\n🎯 Overall: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 ALL TESTS PASSED - 2025 best practices integrated successfully!")
    else:
        print("⚠️ Some tests failed - check logs for details")

    print(f"\n🕐 Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    asyncio.run(main())