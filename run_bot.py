#!/usr/bin/env python3
"""
Bot Runner with Telegram Polling
Simple polling-based bot runner for testing
"""

import os
import sys
import asyncio
import logging
import httpx
from datetime import datetime
import signal

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Setup logging with optional file handler (controlled by LOG_TO_FILE=1)
logger = logging.getLogger("bot_runner")
logger.setLevel(logging.INFO)
fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")

# Console handler (always on)
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
ch.setFormatter(fmt)
logger.addHandler(ch)

# Optional file handler
if os.getenv("LOG_TO_FILE", "0") == "1":
    try:
        fh = logging.FileHandler("bot_run.log", encoding="utf-8")
        fh.setLevel(logging.INFO)
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except Exception as e:
        logger.warning("File logging disabled (reason: %s). Using console only.", e)

class BotRunner:
    """Simple bot runner with long polling"""

    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self.api_base = f"https://api.telegram.org/bot{bot_token}"
        self.bot = None
        self.running = False
        self.offset = 0

    async def initialize_bot(self):
        """Initialize the bot instance with GPT5Service singleton"""
        try:
            logger.info("🤖 Initializing bot...")

            # Initialize GPT5Service singleton first
            logger.info("🔮 Creating GPT5Service singleton...")
            from gpt5_service_new import GPT5Service

            try:
                gpt5 = GPT5Service()
                logger.info("✅ GPT5Service created successfully")

                # Warm-up check via dedicated ping() for minimal cost and fast fail
                logger.info("🔥 Performing GPT-5 warm-up check...")
                if not gpt5.ping():
                    logger.error("❌ GPT-5 warm-up (ping) failed")
                    return False
                logger.info("✅ GPT-5 warm-up successful")

            except Exception as gpt_error:
                logger.error(f"❌ GPT5Service initialization failed: {gpt_error}")
                return False

            # Initialize bot with GPT5Service
            from bot_service.advanced_bot import AdvancedRSSBot
            self.bot = AdvancedRSSBot(self.bot_token, gpt5_service=gpt5)
            logger.info("✅ Bot initialized successfully with GPT-5 singleton")
            return True

        except Exception as e:
            logger.error(f"❌ Bot initialization failed: {e}")
            import traceback
            logger.error(f"📊 Traceback:\n{traceback.format_exc()}")
            return False

    async def get_updates(self) -> list:
        """Get updates from Telegram API"""
        try:
            params = {
                'offset': self.offset,
                'limit': 10,
                'timeout': 30
            }

            logger.debug(f"📡 Getting updates with offset {self.offset}")

            async with httpx.AsyncClient(timeout=35.0) as client:
                response = await client.get(
                    f"{self.api_base}/getUpdates",
                    params=params
                )

                if response.status_code == 200:
                    data = response.json()

                    if data.get('ok'):
                        updates = data.get('result', [])
                        logger.debug(f"📨 Received {len(updates)} updates")
                        return updates
                    else:
                        logger.error(f"❌ API error: {data}")
                        return []
                else:
                    logger.error(f"❌ HTTP error: {response.status_code} - {response.text}")
                    return []

        except Exception as e:
            logger.error(f"💥 Error getting updates: {e}")
            return []

    async def process_update(self, update: dict):
        """Process a single update"""
        try:
            logger.info(f"🔄 Processing update: {update.get('update_id')}")

            if 'message' in update:
                message = update['message']
                logger.info(f"📨 Processing message from user {message.get('from', {}).get('id')}")

                if self.bot:
                    success = await self.bot.process_message(message)
                    if success:
                        logger.info("✅ Message processed successfully")
                    else:
                        logger.warning("⚠️ Message processing returned False")
                else:
                    logger.error("❌ Bot not initialized")

            elif 'callback_query' in update:
                callback_query = update['callback_query']
                logger.info(f"🔘 Processing callback query from user {callback_query.get('from', {}).get('id')}")

                if self.bot:
                    success = await self.bot.process_callback_query(callback_query)
                    if success:
                        logger.info("✅ Callback query processed successfully")
                    else:
                        logger.warning("⚠️ Callback query processing returned False")
                else:
                    logger.error("❌ Bot not initialized")

            # Update offset
            self.offset = update.get('update_id', 0) + 1

        except Exception as e:
            logger.error(f"💥 Error processing update: {e}")
            import traceback
            logger.error(f"📊 Traceback:\n{traceback.format_exc()}")

    async def run_polling(self):
        """Run the bot with long polling"""
        logger.info("🚀 Starting bot polling...")
        self.running = True

        while self.running:
            try:
                updates = await self.get_updates()

                for update in updates:
                    await self.process_update(update)

                if not updates:
                    # Small delay if no updates
                    await asyncio.sleep(1)

            except KeyboardInterrupt:
                logger.info("⏹️ Received keyboard interrupt")
                break
            except Exception as e:
                logger.error(f"💥 Error in polling loop: {e}")
                await asyncio.sleep(5)

        logger.info("🛑 Polling stopped")

    def stop(self):
        """Stop the bot"""
        logger.info("🛑 Stopping bot...")
        self.running = False

async def test_bot_token():
    """Test bot token validity"""
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')

    if not bot_token:
        logger.error("❌ TELEGRAM_BOT_TOKEN not set")
        return False

    try:
        logger.info("🔑 Testing bot token...")
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"https://api.telegram.org/bot{bot_token}/getMe")

        if response.status_code == 200:
            bot_info = response.json()
            if bot_info.get('ok'):
                info = bot_info['result']
                logger.info(f"✅ Bot token valid: @{info.get('username', 'unknown')}")
                return True
            else:
                logger.error(f"❌ Bot API error: {bot_info}")
                return False
        else:
            logger.error(f"❌ HTTP error: {response.status_code}")
            return False

    except Exception as e:
        logger.error(f"💥 Token test failed: {e}")
        return False

async def main():
    """Main function"""
    logger.info("🚀 Starting RSS Bot Runner")
    logger.info(f"🕐 Started at: {datetime.now()}")

    # Check environment
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    pg_dsn = os.getenv('PG_DSN')

    if not bot_token:
        logger.error("❌ TELEGRAM_BOT_TOKEN environment variable not set")
        logger.error("💡 Set it with: set TELEGRAM_BOT_TOKEN=your_token_here")
        return

    if not pg_dsn:
        logger.error("❌ PG_DSN environment variable not set")
        logger.error("💡 Set it with: set PG_DSN=postgresql://user:pass@host:port/db")
        return

    # Test bot token
    if not await test_bot_token():
        logger.error("❌ Bot token test failed")
        return

    # Create and initialize runner
    runner = BotRunner(bot_token)

    if not await runner.initialize_bot():
        logger.error("❌ Bot initialization failed")
        return

    # Setup signal handler
    def signal_handler(signum, frame):
        logger.info(f"📡 Received signal {signum}")
        runner.stop()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        logger.info("🔄 Starting polling loop...")
        logger.info("📱 Send /help to your bot to test!")
        await runner.run_polling()

    except KeyboardInterrupt:
        logger.info("⏹️ Interrupted by user")
    except Exception as e:
        logger.error(f"💥 Runner crashed: {e}")
    finally:
        runner.stop()
        logger.info("🏁 Bot runner stopped")

if __name__ == "__main__":
    # Check Python version
    if sys.version_info < (3, 7):
        print("❌ Python 3.7+ required")
        sys.exit(1)

    # Check required packages
    try:
        import httpx
        import asyncio
    except ImportError as e:
        print(f"❌ Missing required package: {e}")
        print("💡 Install with: pip install httpx")
        sys.exit(1)

    asyncio.run(main())
