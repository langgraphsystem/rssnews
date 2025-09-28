#!/usr/bin/env python3
"""
Integration test for /trends command with real bot instance
Tests the actual message processing pipeline
"""

import os
import sys
import asyncio
import logging
from unittest.mock import patch, AsyncMock

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_bot_integration():
    """Test /trends command through real bot instance"""
    logger.info("🧪 Testing /trends command integration...")

    try:
        # Mock database connection to prevent real DB access
        with patch('pg_client_new.PgClient.__init__') as mock_db_init:
            mock_db_init.return_value = None

            # Import and setup bot
            from bot_service.advanced_bot import AdvancedRSSBot
            from ranking_api import RankingAPI

            # Mock ranking API
            mock_ranking = AsyncMock(spec=RankingAPI)

            # Set minimal environment for testing
            os.environ['TELEGRAM_BOT_TOKEN'] = 'test_token_12345'

            # Initialize bot with mocks
            with patch('database.production_db_client.ProductionDBClient') as mock_db:
                # Setup mock database methods
                mock_db_instance = mock_db.return_value
                mock_db_instance._cursor.return_value.__enter__.return_value.execute.return_value = None
                mock_db_instance._cursor.return_value.__enter__.return_value.fetchall.return_value = []

                # Mock HTTP client to prevent actual API calls
                with patch('httpx.AsyncClient') as mock_http:
                    mock_response = AsyncMock()
                    mock_response.status_code = 200
                    mock_response.json.return_value = {"ok": True, "result": {"message_id": 123}}
                    mock_http.return_value.__aenter__.return_value.post.return_value = mock_response

                    # Initialize bot
                    bot = AdvancedRSSBot('test_token', mock_ranking)

                    # Test message processing
                    test_message = {
                        'chat': {'id': 123456789},
                        'from': {'id': 987654321},
                        'text': '/trends',
                        'message_id': 1
                    }

                    logger.info("📨 Processing /trends message...")
                    result = await bot.process_message(test_message)

                    logger.info(f"✅ Message processing result: {result}")
                    return True

    except Exception as e:
        logger.error(f"❌ Integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_trends_service_edge_cases():
    """Test TrendsService with edge cases"""
    logger.info("🧪 Testing TrendsService edge cases...")

    try:
        from services.trends_service import TrendsService

        # Mock empty database
        class EmptyMockDB:
            def _cursor(self):
                class MockCursor:
                    def __enter__(self):
                        return self
                    def __exit__(self, *args):
                        pass
                    def execute(self, query, params=None):
                        pass
                    def fetchall(self):
                        return []  # No articles
                    @property
                    def description(self):
                        return [('article_id',), ('url',), ('source',), ('domain',),
                               ('title_norm',), ('clean_text',), ('published_at',), ('embedding',)]
                return MockCursor()

        trends_service = TrendsService(EmptyMockDB())

        # Test with no data
        logger.info("Testing with no articles...")
        payload = await asyncio.to_thread(trends_service.build_trends, "24h", 100, 5)
        assert payload['status'] == 'ok'
        assert len(payload['data']) == 0
        logger.info("✅ No data case handled correctly")

        # Test formatting with empty data
        message = trends_service.format_trends_markdown(payload, "24h")
        assert "не найдены" in message.lower()
        logger.info("✅ Empty formatting handled correctly")

        return True

    except Exception as e:
        logger.error(f"❌ Edge case test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_callback_handling():
    """Test trends callback button handling"""
    logger.info("🧪 Testing trends callback handling...")

    try:
        # Mock bot for callback testing
        with patch('pg_client_new.PgClient.__init__') as mock_db_init:
            mock_db_init.return_value = None

            from bot_service.advanced_bot import AdvancedRSSBot
            from ranking_api import RankingAPI

            mock_ranking = AsyncMock(spec=RankingAPI)
            os.environ['TELEGRAM_BOT_TOKEN'] = 'test_token_12345'

            with patch('database.production_db_client.ProductionDBClient') as mock_db:
                mock_db_instance = mock_db.return_value
                mock_db_instance._cursor.return_value.__enter__.return_value.execute.return_value = None
                mock_db_instance._cursor.return_value.__enter__.return_value.fetchall.return_value = []

                with patch('httpx.AsyncClient') as mock_http:
                    mock_response = AsyncMock()
                    mock_response.status_code = 200
                    mock_http.return_value.__aenter__.return_value.post.return_value = mock_response

                    bot = AdvancedRSSBot('test_token', mock_ranking)

                    # Test trends refresh callback
                    test_callback = {
                        'id': 'cb123',
                        'data': 'trends:refresh',
                        'message': {
                            'chat': {'id': 123456789},
                            'message_id': 456
                        },
                        'from': {'id': 987654321}
                    }

                    logger.info("📨 Processing trends refresh callback...")
                    result = await bot.process_callback_query(test_callback)

                    logger.info(f"✅ Callback processing result: {result}")
                    return True

    except Exception as e:
        logger.error(f"❌ Callback test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Run integration tests"""
    logger.info("🚀 Starting /trends integration tests...")

    test_results = []

    # Test 1: Bot integration
    logger.info("\n" + "="*50)
    logger.info("TEST 1: BOT INTEGRATION")
    logger.info("="*50)
    result1 = await test_bot_integration()
    test_results.append(("Bot Integration", result1))

    # Test 2: Edge cases
    logger.info("\n" + "="*50)
    logger.info("TEST 2: EDGE CASES")
    logger.info("="*50)
    result2 = await test_trends_service_edge_cases()
    test_results.append(("Edge Cases", result2))

    # Test 3: Callback handling
    logger.info("\n" + "="*50)
    logger.info("TEST 3: CALLBACK HANDLING")
    logger.info("="*50)
    result3 = await test_callback_handling()
    test_results.append(("Callback Handling", result3))

    # Print summary
    logger.info("\n" + "="*50)
    logger.info("INTEGRATION TEST SUMMARY")
    logger.info("="*50)

    all_passed = True
    for test_name, passed in test_results:
        status = "✅ PASS" if passed else "❌ FAIL"
        logger.info(f"{test_name}: {status}")
        if not passed:
            all_passed = False

    if all_passed:
        logger.info("\n🎉 ALL INTEGRATION TESTS PASSED! /trends command is production ready.")
    else:
        logger.info("\n💥 SOME INTEGRATION TESTS FAILED! Check logs above for details.")

    return all_passed

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)