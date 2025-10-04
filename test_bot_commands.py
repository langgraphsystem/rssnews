#!/usr/bin/env python3
"""
Comprehensive Bot Command Testing Script
Tests all Phase 2-3 commands with real data
"""

import os
import sys
import asyncio
import logging
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from bot_service.advanced_bot import AdvancedRSSBot
from gpt5_service_new import GPT5Service
from pg_client_new import PgClient


async def test_bot_commands():
    """Test all bot commands end-to-end"""

    print("=" * 80)
    print("🤖 RSS News Telegram Bot - Command Testing Suite")
    print("=" * 80)
    print(f"📅 Test Date: {datetime.now()}")
    print()

    # Initialize services
    print("🔧 Initializing services...")
    try:
        db = PgClient()
        gpt5 = GPT5Service()

        # Test GPT-5 warm-up
        print("🔥 Testing GPT-5 connection...")
        if not gpt5.ping():
            print("❌ GPT-5 ping failed")
            return False
        print("✅ GPT-5 ready")

        # Initialize Claude (optional)
        claude_service = None
        try:
            from services.claude_service import create_claude_service
            claude_service = create_claude_service()
            print("✅ Claude Service ready")
        except Exception as e:
            print(f"⚠️  Claude Service unavailable: {e}")

        # Initialize bot
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        bot = AdvancedRSSBot(bot_token, gpt5_service=gpt5, claude_service=claude_service)
        print("✅ Bot initialized")
        print()

    except Exception as e:
        print(f"❌ Service initialization failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Test chat ID (use env var - must be valid Telegram chat)
    test_chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not test_chat_id:
        print("❌ TELEGRAM_CHAT_ID not set - cannot send messages")
        print("📝 Set TELEGRAM_CHAT_ID to your Telegram chat ID")
        return False

    test_user_id = test_chat_id

    # Test results tracking
    results = {
        'total': 0,
        'passed': 0,
        'failed': 0,
        'skipped': 0,
        'details': []
    }

    def record_result(command, status, message=""):
        results['total'] += 1
        results[status] += 1
        results['details'].append({
            'command': command,
            'status': status,
            'message': message
        })
        status_emoji = {'passed': '✅', 'failed': '❌', 'skipped': '⏭️'}
        print(f"{status_emoji.get(status, '❓')} {command}: {message}")

    print("=" * 80)
    print("📋 TESTING PHASE 2-3 COMMANDS")
    print("=" * 80)
    print()

    # Test 1: /search command
    print("1️⃣  Testing /search command (embedding-based search)...")
    try:
        result = await bot.handle_search_command(
            chat_id=test_chat_id,
            user_id=test_user_id,
            query="Trump election latest news"
        )
        if result:
            record_result("/search", "passed", "Search returned results")
        else:
            record_result("/search", "failed", "No results returned")
    except Exception as e:
        record_result("/search", "failed", str(e))
    print()

    # Test 2: /analyze command
    print("2️⃣  Testing /analyze command (Claude analysis)...")
    try:
        if claude_service:
            result = await bot.handle_analyze_command(
                chat_id=test_chat_id,
                user_id=test_user_id,
                args=["Trump", "Biden", "politics"]
            )
            if result:
                record_result("/analyze", "passed", "Analysis completed")
            else:
                record_result("/analyze", "failed", "Analysis failed")
        else:
            record_result("/analyze", "skipped", "Claude service not available")
    except Exception as e:
        record_result("/analyze", "failed", str(e))
    print()

    # Test 3: /trends command
    print("3️⃣  Testing /trends command (Claude Sonnet 4 trend analysis)...")
    try:
        if claude_service:
            result = await bot.handle_trends_command(
                chat_id=test_chat_id,
                user_id=test_user_id,
                args=["7d"]  # Last 7 days
            )
            if result:
                record_result("/trends", "passed", "Trends analysis completed")
            else:
                record_result("/trends", "failed", "Trends failed")
        else:
            record_result("/trends", "skipped", "Claude service not available")
    except Exception as e:
        record_result("/trends", "failed", str(e))
    print()

    # Test 4: /summarize command
    print("4️⃣  Testing /summarize command...")
    try:
        result = await bot.handle_summarize_command(
            chat_id=test_chat_id,
            user_id=test_user_id,
            args=["Arizona shooting"]
        )
        if result:
            record_result("/summarize", "passed", "Summarization completed")
        else:
            record_result("/summarize", "failed", "Summarization failed")
    except Exception as e:
        record_result("/summarize", "failed", str(e))
    print()

    # Test 5: /aggregate command
    print("5️⃣  Testing /aggregate command...")
    try:
        result = await bot.handle_aggregate_command(
            chat_id=test_chat_id,
            user_id=test_user_id,
            args=["election", "news"]
        )
        if result:
            record_result("/aggregate", "passed", "Aggregation completed")
        else:
            record_result("/aggregate", "failed", "Aggregation failed")
    except Exception as e:
        record_result("/aggregate", "failed", str(e))
    print()

    # Test 6: /ask command (GPT-5)
    print("6️⃣  Testing /ask command (GPT-5 RAG)...")
    try:
        result = await bot.handle_ask_command(
            chat_id=test_chat_id,
            user_id=test_user_id,
            query="What are the latest developments in US politics?"
        )
        if result:
            record_result("/ask", "passed", "GPT-5 RAG response generated")
        else:
            record_result("/ask", "failed", "GPT-5 RAG failed")
    except Exception as e:
        record_result("/ask", "failed", str(e))
    print()

    # Print final summary
    print()
    print("=" * 80)
    print("📊 TEST SUMMARY")
    print("=" * 80)
    print(f"Total Tests: {results['total']}")
    print(f"✅ Passed: {results['passed']}")
    print(f"❌ Failed: {results['failed']}")
    print(f"⏭️  Skipped: {results['skipped']}")
    print()

    if results['failed'] > 0:
        print("❌ FAILED TESTS:")
        for detail in results['details']:
            if detail['status'] == 'failed':
                print(f"  - {detail['command']}: {detail['message']}")
        print()

    success_rate = (results['passed'] / results['total'] * 100) if results['total'] > 0 else 0
    print(f"Success Rate: {success_rate:.1f}%")
    print("=" * 80)

    return results['failed'] == 0


if __name__ == "__main__":
    success = asyncio.run(test_bot_commands())
    sys.exit(0 if success else 1)
