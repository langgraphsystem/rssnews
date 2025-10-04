#!/usr/bin/env python3
"""
Comprehensive bot command testing on Railway production
Tests all commands with real data and API calls
"""
import os
import asyncio
import httpx
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

# Get bot token from environment
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
if not TELEGRAM_BOT_TOKEN:
    print("❌ TELEGRAM_BOT_TOKEN not set")
    exit(1)

# Test chat ID - use your real Telegram chat ID
TEST_CHAT_ID = os.getenv('TEST_CHAT_ID', '123456789')

API_BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


async def send_message(text: str):
    """Send message to Telegram"""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{API_BASE}/sendMessage",
            json={
                "chat_id": TEST_CHAT_ID,
                "text": text,
                "parse_mode": "Markdown"
            }
        )
        result = response.json()
        if result.get('ok'):
            print(f"✅ Sent: {text[:50]}...")
            return True
        else:
            print(f"❌ Failed to send: {result.get('description')}")
            return False


async def get_updates():
    """Get bot updates to see responses"""
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(f"{API_BASE}/getUpdates?offset=-1")
        result = response.json()
        if result.get('ok') and result.get('result'):
            return result['result']
        return []


async def test_command(command: str, description: str, wait_time: int = 3):
    """Test a bot command"""
    print()
    print("=" * 80)
    print(f"🧪 Testing: {command}")
    print(f"📝 Description: {description}")
    print("=" * 80)

    success = await send_message(command)
    if success:
        print(f"⏳ Waiting {wait_time}s for response...")
        await asyncio.sleep(wait_time)
        print("✅ Command sent successfully")
    else:
        print("❌ Command failed")

    return success


async def main():
    """Run all command tests"""
    print("🤖 RSS News Bot - Comprehensive Command Testing")
    print(f"🕐 Started at: {datetime.now()}")
    print(f"📱 Test Chat ID: {TEST_CHAT_ID}")
    print()

    # Check bot info
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{API_BASE}/getMe")
        bot_info = response.json()
        if bot_info.get('ok'):
            bot = bot_info['result']
            print(f"✅ Bot connected: @{bot['username']}")
            print(f"   ID: {bot['id']}")
            print(f"   Name: {bot.get('first_name')}")
        else:
            print("❌ Failed to connect to bot")
            return

    print()
    print("=" * 80)
    print("🎯 Core Commands Testing")
    print("=" * 80)

    # Test core commands
    tests = [
        ("/start", "Welcome message and bot introduction", 2),
        ("/help", "Show all available commands", 2),

        # Phase 2 - Search & Discovery
        ("/search Trump election 2024", "Semantic search with real query", 5),
        ("/search artificial intelligence regulation", "AI regulation search", 5),
        ("/search climate change policy", "Climate policy search", 5),

        # Phase 2 - Analysis
        ("/analyze Trump election", "Deep analysis with Claude Sonnet 4", 10),
        ("/analyze AI regulation EU", "EU AI regulation analysis", 10),

        # Phase 2 - Trends
        ("/trends", "Trending topics detection", 8),
        ("/trends politics", "Politics trends", 8),

        # Phase 2 - Summarization
        ("/summarize Ukraine war", "Multi-article summarization", 8),
        ("/summarize US economy", "Economy summary", 8),

        # Phase 3 - RAG & Ask
        ("/ask What are the latest developments in AI regulation?", "RAG-style question answering", 8),
        ("/ask Who won the recent elections?", "Election question", 8),

        # Quality & Settings
        ("/quality", "Quality insights", 3),
        ("/settings", "User settings", 2),

        # Database commands (admin)
        ("/db_stats", "Database statistics", 3),
        ("/db_tables", "Database tables info", 3),

        # Advanced features
        ("/brief today", "Daily news brief", 5),
        ("/insights tech", "Tech insights", 5),
        ("/sentiment Trump", "Sentiment analysis", 5),
        ("/topics", "Topic detection", 5),
    ]

    results = []
    for command, description, wait_time in tests:
        success = await test_command(command, description, wait_time)
        results.append({
            'command': command,
            'description': description,
            'success': success
        })

    # Summary
    print()
    print("=" * 80)
    print("📊 Test Summary")
    print("=" * 80)
    total = len(results)
    successful = sum(1 for r in results if r['success'])

    print(f"Total commands tested: {total}")
    print(f"Successful: {successful}")
    print(f"Failed: {total - successful}")
    print(f"Success rate: {successful/total*100:.1f}%")
    print()

    if total - successful > 0:
        print("❌ Failed commands:")
        for r in results:
            if not r['success']:
                print(f"  - {r['command']}")

    print()
    print("=" * 80)
    print("💡 Next Steps:")
    print("=" * 80)
    print("1. Check your Telegram chat for bot responses")
    print("2. Verify each command output for correctness")
    print("3. Note any errors or unexpected behavior")
    print("4. Test interactive buttons and callbacks manually")
    print()
    print(f"🕐 Completed at: {datetime.now()}")


if __name__ == "__main__":
    asyncio.run(main())
