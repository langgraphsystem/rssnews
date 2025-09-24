#!/usr/bin/env python3
"""
Telegram Bot Starter for Railway
Starts the RSS News Telegram bot with 2025 best practices
"""

import os
import sys
import asyncio
import logging
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

def main():
    """Main function to start Telegram bot"""
    print("🚀 RSS News Telegram Bot Starter")
    print("=" * 50)
    print(f"🕐 Started at: {datetime.now()}")
    print()

    # Check environment variables
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    pg_dsn = os.getenv('PG_DSN')

    print("🔍 Checking environment variables...")
    print(f"  TELEGRAM_BOT_TOKEN: {'✅ Set' if bot_token else '❌ Missing'}")
    print(f"  PG_DSN: {'✅ Set' if pg_dsn else '❌ Missing'}")
    print()

    if not bot_token:
        logger.error("❌ TELEGRAM_BOT_TOKEN environment variable not set")
        print("💡 This should be set in Railway dashboard")
        return 1

    if not pg_dsn:
        logger.error("❌ PG_DSN environment variable not set")
        print("💡 This should be set in Railway dashboard")
        return 1

    try:
        print("🤖 Starting RSS News Telegram Bot...")
        print("📱 Bot: @rssnewsusabot")
        print("🚦 2025 Rate Limiting: ✅")
        print("🚨 Advanced Error Handling: ✅")
        print("📊 Structured Logging: ✅")
        print()

        # Import and run bot
        from run_bot import main as run_bot_main

        logger.info("Starting Telegram bot with 2025 best practices")
        asyncio.run(run_bot_main())

    except KeyboardInterrupt:
        logger.info("⏹️ Bot stopped by user")
        print("⏹️ Bot stopped")
        return 0
    except Exception as e:
        logger.error(f"💥 Bot failed: {e}")
        print(f"❌ Bot failed: {e}")
        return 1

    return 0

if __name__ == "__main__":
    exit(main())