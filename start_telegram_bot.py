#!/usr/bin/env python3
"""
Telegram Bot Starter for Railway
Starts the RSS News Telegram bot with 2025 best practices
"""

import os
import sys
import asyncio
import logging
import argparse
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

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

    # Debug: Print all environment variables starting with TELEGRAM and PG
    print("🔍 Environment variables debugging:")
    all_env = dict(os.environ)
    for key, value in sorted(all_env.items()):
        if key.startswith(('TELEGRAM', 'PG_', 'RAILWAY')):
            print(f"  {key}: {value[:50]}..." if len(str(value)) > 50 else f"  {key}: {value}")
    print()

    # CLI args
    parser = argparse.ArgumentParser(description="Start RSS News Telegram bot")
    parser.add_argument("--check", action="store_true", help="Validate environment and exit")
    args, _ = parser.parse_known_args()

    # Check environment variables with fallbacks
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    pg_dsn = os.getenv('PG_DSN')
    openai_api_key = os.getenv('OPENAI_API_KEY')

    # Try alternative environment variable patterns that Railway might use
    if not bot_token:
        bot_token = os.getenv('TELEGRAM_BOT_TOKEN_SECRET')

    # Always try to construct from Railway database variables since we see them in railway variables
    if not pg_dsn:
        db_host = os.getenv('DB_HOST')
        db_user = os.getenv('DB_USER')
        db_pass = os.getenv('DB_PASS')
        db_name = os.getenv('DB_NAME')
        db_port = os.getenv('DB_PORT', '12306')  # Railway's port

        if all([db_host, db_user, db_pass, db_name]):
            pg_dsn = f"postgresql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}?sslmode=disable"
            print(f"🔧 Constructed PG_DSN from Railway DB vars: {pg_dsn[:50]}...")
        else:
            print(f"🔍 Missing DB vars - host:{bool(db_host)} user:{bool(db_user)} pass:{bool(db_pass)} name:{bool(db_name)}")

    # No hardcoded fallbacks — must come from Railway env
    if not bot_token:
        print("❌ TELEGRAM_BOT_TOKEN не найден в окружении Railway")
        return 1
    if not pg_dsn:
        print("❌ PG_DSN не найден в окружении Railway")
        return 1

    # Require OpenAI key from Railway env for GPT-5 features
    if not openai_api_key:
        print("❌ OPENAI_API_KEY не найден в окружении Railway (требуется для GPT-5)")
        return 1

    print("🔍 Final environment check:")
    print(f"  TELEGRAM_BOT_TOKEN: {'✅ Set' if bot_token else '❌ Missing'}")
    print(f"  PG_DSN: {'✅ Set' if pg_dsn else '❌ Missing'}")
    print(f"  OPENAI_API_KEY: {'✅ Set' if openai_api_key else '❌ Missing'}")
    print()

    # Health-check mode: only validate env and exit
    if args.check:
        if bot_token and pg_dsn and openai_api_key:
            print("✅ Environment check passed")
            return 0
        else:
            print("❌ Environment check failed — missing variables")
            return 1

    if not bot_token:
        logger.error("❌ TELEGRAM_BOT_TOKEN environment variable not set")
        print("💡 Available env vars:", [k for k in os.environ.keys() if 'TELEGRAM' in k])
        return 1

    if not pg_dsn:
        logger.error("❌ PG_DSN environment variable not set")
        print("💡 Available DB vars:", [k for k in os.environ.keys() if k.startswith('DB_')])
        return 1

    # Set the environment variables for child processes
    os.environ['TELEGRAM_BOT_TOKEN'] = bot_token
    os.environ['PG_DSN'] = pg_dsn
    os.environ['OPENAI_API_KEY'] = openai_api_key

    try:
        print("🤖 Starting RSS News Telegram Bot...")
        print("📱 Bot: @rssnewsusabot")
        print("🚦 2025 Rate Limiting: ✅")
        print("🚨 Advanced Error Handling: ✅")
        print("📊 Structured Logging: ✅")
        print()

        # Start health check server in background
        from health_server import start_health_server
        health_port = int(os.getenv('PORT', '8080'))
        health_server = start_health_server(health_port)
        if health_server:
            print(f"🏥 Health check server running on port {health_port}")
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
