#!/usr/bin/env python3
"""
Simple Bot Test Script
Tests basic bot functionality and connection
"""

import os
import sys
import asyncio
import logging
import json
from datetime import datetime

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot_test.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

async def test_bot_initialization():
    """Test bot initialization"""
    logger.info("🧪 Testing bot initialization...")

    try:
        # Check environment variables
        bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        pg_dsn = os.getenv('PG_DSN')

        logger.info(f"🔑 Bot token present: {'Yes' if bot_token else 'No'}")
        logger.info(f"🗄️ Database DSN present: {'Yes' if pg_dsn else 'No'}")

        if not bot_token:
            logger.error("❌ TELEGRAM_BOT_TOKEN not set!")
            return False

        if not pg_dsn:
            logger.error("❌ PG_DSN not set!")
            return False

        # Try to import bot
        logger.info("📦 Importing bot module...")
        from bot_service.advanced_bot import AdvancedRSSBot

        # Initialize bot
        logger.info("🤖 Creating bot instance...")
        bot = AdvancedRSSBot(bot_token)

        logger.info("✅ Bot initialization successful!")
        return True

    except Exception as e:
        logger.error(f"❌ Bot initialization failed: {e}")
        import traceback
        logger.error(f"📊 Traceback:\n{traceback.format_exc()}")
        return False

async def test_telegram_api_connection():
    """Test Telegram API connection"""
    logger.info("🧪 Testing Telegram API connection...")

    try:
        import httpx
        bot_token = os.getenv('TELEGRAM_BOT_TOKEN')

        if not bot_token:
            logger.error("❌ No bot token for API test")
            return False

        api_url = f"https://api.telegram.org/bot{bot_token}/getMe"
        logger.info(f"📡 Testing API endpoint: {api_url}")

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(api_url)

            logger.info(f"📡 API Response status: {response.status_code}")

            if response.status_code == 200:
                bot_info = response.json()
                logger.info(f"🤖 Bot info: {json.dumps(bot_info, indent=2)}")
                logger.info("✅ Telegram API connection successful!")
                return True
            else:
                logger.error(f"❌ API Error: {response.text}")
                return False

    except Exception as e:
        logger.error(f"❌ API connection test failed: {e}")
        return False

async def test_database_connection():
    """Test database connection"""
    logger.info("🧪 Testing database connection...")

    try:
        from database.production_db_client import ProductionDBClient

        logger.info("🗄️ Creating database client...")
        db = ProductionDBClient()

        logger.info("📊 Getting analytics...")
        stats = db.get_search_analytics()

        logger.info(f"📈 Database stats: {json.dumps(stats, indent=2)}")
        logger.info("✅ Database connection successful!")
        return True

    except Exception as e:
        logger.error(f"❌ Database connection test failed: {e}")
        import traceback
        logger.error(f"📊 Traceback:\n{traceback.format_exc()}")
        return False

async def test_message_processing():
    """Test message processing"""
    logger.info("🧪 Testing message processing...")

    try:
        from bot_service.advanced_bot import AdvancedRSSBot

        bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        if not bot_token:
            logger.error("❌ No bot token for message test")
            return False

        bot = AdvancedRSSBot(bot_token)

        # Test message
        test_message = {
            'chat': {'id': 123456789},
            'from': {'id': 123456789, 'first_name': 'Test'},
            'text': '/help',
            'message_id': 1,
            'date': int(datetime.now().timestamp())
        }

        logger.info(f"📨 Testing message: {json.dumps(test_message, indent=2)}")

        success = await bot.process_message(test_message)

        if success:
            logger.info("✅ Message processing successful!")
            return True
        else:
            logger.error("❌ Message processing failed")
            return False

    except Exception as e:
        logger.error(f"❌ Message processing test failed: {e}")
        import traceback
        logger.error(f"📊 Traceback:\n{traceback.format_exc()}")
        return False

async def main():
    """Run all tests"""
    logger.info("🚀 Starting bot test suite...")
    logger.info(f"🕐 Test started at: {datetime.now()}")

    tests = [
        ("Bot Initialization", test_bot_initialization),
        ("Telegram API Connection", test_telegram_api_connection),
        ("Database Connection", test_database_connection),
        ("Message Processing", test_message_processing),
    ]

    results = {}

    for test_name, test_func in tests:
        logger.info(f"\n{'='*50}")
        logger.info(f"🧪 Running test: {test_name}")
        logger.info(f"{'='*50}")

        try:
            result = await test_func()
            results[test_name] = result

            if result:
                logger.info(f"✅ {test_name}: PASSED")
            else:
                logger.error(f"❌ {test_name}: FAILED")

        except Exception as e:
            logger.error(f"💥 {test_name}: CRASHED - {e}")
            results[test_name] = False

    # Summary
    logger.info(f"\n{'='*50}")
    logger.info("📊 TEST SUMMARY")
    logger.info(f"{'='*50}")

    passed = sum(1 for r in results.values() if r)
    total = len(results)

    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        logger.info(f"{status}: {test_name}")

    logger.info(f"\n🎯 Overall: {passed}/{total} tests passed")

    if passed == total:
        logger.info("🎉 All tests passed! Bot should be working correctly.")
    else:
        logger.warning(f"⚠️ {total - passed} tests failed. Check logs for issues.")

    logger.info(f"🕐 Test completed at: {datetime.now()}")

if __name__ == "__main__":
    # Check environment first
    required_vars = ['TELEGRAM_BOT_TOKEN', 'PG_DSN']
    missing_vars = [var for var in required_vars if not os.getenv(var)]

    if missing_vars:
        print(f"❌ Missing environment variables: {missing_vars}")
        print("Please set:")
        for var in missing_vars:
            print(f"  set {var}=your_value_here")
        sys.exit(1)

    asyncio.run(main())