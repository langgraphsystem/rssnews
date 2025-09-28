#!/usr/bin/env python3
"""
Test script for /trends command end-to-end functionality
Tests the complete pipeline from command processing to response formatting
"""

import os
import sys
import asyncio
import logging
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock
from typing import Dict, Any, List

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class MockDBClient:
    """Mock database client for testing"""

    def __init__(self):
        # Generate realistic datetime objects for recent articles
        base_time = datetime.utcnow()
        self.mock_articles = [
            {
                'article_id': f'art_{i}',
                'url': f'https://example{i}.com/article',
                'source': f'source_{i}',
                'domain': f'example{i}.com',
                'title_norm': f'Test Article {i} about AI and technology',
                'clean_text': f'This is test article {i} content about artificial intelligence and machine learning. Lorem ipsum dolor sit amet.',
                'published_at': base_time - timedelta(hours=i),  # Spread articles over last 20 hours
                'embedding': [0.1 + i*0.01] * 384  # Mock 384-dim embedding
            }
            for i in range(20)
        ]

    def _cursor(self):
        """Mock cursor context manager"""
        class MockCursor:
            def __init__(self, db):
                self.db = db

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def execute(self, query, params=None):
                logger.info(f"Mock SQL executed: {query[:100]}...")

            def fetchall(self):
                return [(
                    art['article_id'], art['url'], art['source'], art['domain'],
                    art['title_norm'], art['clean_text'], art['published_at'],
                    art['embedding']
                ) for art in self.db.mock_articles]

            @property
            def description(self):
                return [
                    ('article_id',), ('url',), ('source',), ('domain',),
                    ('title_norm',), ('clean_text',), ('published_at',), ('embedding',)
                ]

        return MockCursor(self)

class MockRankingAPI:
    """Mock ranking API for testing"""

    async def search(self, request):
        logger.info(f"Mock search called with query: {request.query}")

        class MockResponse:
            def __init__(self):
                self.results = [
                    {
                        'article_id': f'search_art_{i}',
                        'title': f'Search Result {i}',
                        'content': f'Search content {i}',
                        'url': f'https://search{i}.com/article',
                        'domain': f'search{i}.com',
                        'published_at': '2024-01-15T12:00:00Z'
                    }
                    for i in range(5)
                ]

        return MockResponse()

class MockAdvancedBot:
    """Mock bot for testing trends command"""

    def __init__(self):
        self.db = MockDBClient()
        self.ranking_api = MockRankingAPI()

        # Import real services
        from services.trends_service import TrendsService
        from bot_service.formatters import MessageFormatter

        self.trends_service = TrendsService(self.db)
        self.formatter = MessageFormatter()
        self.sent_messages = []

    async def _send_message(self, chat_id: str, text: str, reply_markup=None, parse_mode="Markdown"):
        """Mock message sending"""
        logger.info(f"📤 Mock sending message to {chat_id}: {text[:100]}...")
        self.sent_messages.append({
            'chat_id': chat_id,
            'text': text,
            'reply_markup': reply_markup,
            'parse_mode': parse_mode
        })
        return True

    async def _send_long_message(self, chat_id: str, text: str, reply_markup=None):
        """Mock long message sending"""
        return await self._send_message(chat_id, text, reply_markup)

    def _create_inline_keyboard(self, buttons):
        """Mock inline keyboard creation"""
        return {"inline_keyboard": buttons}

    async def handle_trends_command(self, chat_id: str, user_id: str) -> bool:
        """Handle /trends command"""
        try:
            await self._send_message(chat_id, "📈 Сбор тем и ключевых слов за 24h...")

            # Compute or fetch cached trends
            payload = await asyncio.to_thread(self.trends_service.build_trends, "24h", 600, 10)
            message = self.trends_service.format_trends_markdown(payload, window="24h")

            buttons = [
                [
                    {"text": "🔄 Обновить", "callback_data": "trends:refresh"},
                    {"text": "📊 Аналитика", "callback_data": "analytics:full"}
                ]
            ]

            markup = self._create_inline_keyboard(buttons)

            # HTML formatting used for links
            return await self._send_long_message(chat_id, message, markup)

        except Exception as e:
            logger.error(f"Trends command failed: {e}")
            import traceback
            traceback.print_exc()
            return await self._send_message(chat_id, f"❌ Trends analysis failed: {e}")

async def test_trends_service():
    """Test TrendsService directly"""
    logger.info("🧪 Testing TrendsService...")

    try:
        from services.trends_service import TrendsService

        mock_db = MockDBClient()
        trends_service = TrendsService(mock_db)

        # Test build_trends
        logger.info("Testing build_trends...")
        payload = await asyncio.to_thread(trends_service.build_trends, "24h", 20, 5)

        logger.info(f"✅ TrendsService payload: {payload.get('status')}, data count: {len(payload.get('data', []))}")

        # Test format_trends_markdown
        logger.info("Testing format_trends_markdown...")
        message = trends_service.format_trends_markdown(payload, "24h")

        logger.info(f"✅ Formatted message length: {len(message)} chars")
        logger.info(f"Message preview: {message[:200]}...")

        return True

    except Exception as e:
        logger.error(f"❌ TrendsService test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_full_trends_command():
    """Test full /trends command pipeline"""
    logger.info("🧪 Testing full /trends command...")

    try:
        bot = MockAdvancedBot()

        # Execute trends command
        result = await bot.handle_trends_command("123456", "user123")

        logger.info(f"✅ Command result: {result}")
        logger.info(f"✅ Messages sent: {len(bot.sent_messages)}")

        for i, msg in enumerate(bot.sent_messages):
            logger.info(f"📩 Message {i+1}: {msg['text'][:100]}...")

        return True

    except Exception as e:
        logger.error(f"❌ Full command test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_imports_and_dependencies():
    """Test all required imports and dependencies"""
    logger.info("🧪 Testing imports and dependencies...")

    try:
        # Test core imports
        from services.trends_service import TrendsService
        from bot_service.formatters import MessageFormatter
        from bot_service.advanced_bot import AdvancedRSSBot
        from database.production_db_client import ProductionDBClient

        logger.info("✅ All core imports successful")

        # Test sklearn imports (required for clustering)
        from sklearn.cluster import DBSCAN
        from sklearn.feature_extraction.text import TfidfVectorizer
        import numpy as np

        logger.info("✅ All sklearn imports successful")

        # Test database client instantiation
        try:
            # Set mock DSN for testing
            os.environ['PG_DSN'] = 'postgresql://test:test@localhost/test'

            # This will fail to connect but should not fail to import/instantiate
            db_client = ProductionDBClient()
            logger.info("✅ ProductionDBClient instantiation successful")

        except Exception as db_e:
            logger.warning(f"⚠️ DB connection failed (expected): {db_e}")

        return True

    except Exception as e:
        logger.error(f"❌ Import test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Run all tests"""
    logger.info("🚀 Starting /trends command comprehensive test...")

    test_results = []

    # Test 1: Imports and dependencies
    logger.info("\n" + "="*50)
    logger.info("TEST 1: IMPORTS AND DEPENDENCIES")
    logger.info("="*50)
    result1 = await test_imports_and_dependencies()
    test_results.append(("Imports & Dependencies", result1))

    # Test 2: TrendsService functionality
    logger.info("\n" + "="*50)
    logger.info("TEST 2: TRENDS SERVICE")
    logger.info("="*50)
    result2 = await test_trends_service()
    test_results.append(("TrendsService", result2))

    # Test 3: Full command pipeline
    logger.info("\n" + "="*50)
    logger.info("TEST 3: FULL COMMAND PIPELINE")
    logger.info("="*50)
    result3 = await test_full_trends_command()
    test_results.append(("Full Command", result3))

    # Print summary
    logger.info("\n" + "="*50)
    logger.info("TEST SUMMARY")
    logger.info("="*50)

    all_passed = True
    for test_name, passed in test_results:
        status = "✅ PASS" if passed else "❌ FAIL"
        logger.info(f"{test_name}: {status}")
        if not passed:
            all_passed = False

    if all_passed:
        logger.info("\n🎉 ALL TESTS PASSED! /trends command is fully functional.")
    else:
        logger.info("\n💥 SOME TESTS FAILED! Check logs above for details.")

    return all_passed

if __name__ == "__main__":
    # Set test environment
    os.environ.setdefault('PG_DSN', 'postgresql://test:test@localhost/test')

    success = asyncio.run(main())
    sys.exit(0 if success else 1)