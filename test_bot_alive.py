#!/usr/bin/env python3
"""Test if Telegram bot is alive and responding"""
import os
import asyncio
import httpx
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
if not TELEGRAM_BOT_TOKEN:
    print("❌ TELEGRAM_BOT_TOKEN not set in .env")
    exit(1)

API_BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


async def main():
    print("🔍 Testing Telegram Bot Status")
    print("=" * 80)
    print()

    async with httpx.AsyncClient(timeout=10.0) as client:
        # 1. Check bot info
        print("1️⃣  Checking bot info via getMe...")
        try:
            response = await client.get(f"{API_BASE}/getMe")
            result = response.json()

            if result.get('ok'):
                bot = result['result']
                print(f"✅ Bot is valid:")
                print(f"   Username: @{bot['username']}")
                print(f"   ID: {bot['id']}")
                print(f"   Name: {bot.get('first_name')}")
                print()
            else:
                print(f"❌ Bot API error: {result}")
                return
        except Exception as e:
            print(f"❌ Failed to connect: {e}")
            return

        # 2. Check webhook status
        print("2️⃣  Checking webhook status...")
        try:
            response = await client.get(f"{API_BASE}/getWebhookInfo")
            result = response.json()

            if result.get('ok'):
                webhook = result['result']
                print(f"Webhook URL: {webhook.get('url', 'Not set (polling mode)')}")
                print(f"Pending updates: {webhook.get('pending_update_count', 0)}")

                if webhook.get('last_error_date'):
                    import datetime
                    error_date = datetime.datetime.fromtimestamp(webhook['last_error_date'])
                    print(f"⚠️  Last error: {webhook.get('last_error_message')} at {error_date}")
                print()
        except Exception as e:
            print(f"⚠️  Webhook check failed: {e}")
            print()

        # 3. Try to get updates (polling mode check)
        print("3️⃣  Checking for recent updates (polling mode)...")
        try:
            response = await client.get(f"{API_BASE}/getUpdates?limit=1")
            result = response.json()

            if result.get('ok'):
                updates = result.get('result', [])
                if updates:
                    print(f"✅ Bot receiving updates (found {len(updates)} recent)")
                    update = updates[0]
                    if 'message' in update:
                        msg = update['message']
                        print(f"   Latest message from chat {msg['chat']['id']}")
                else:
                    print("⚠️  No recent updates (bot might not be polling)")
                print()
        except Exception as e:
            print(f"⚠️  Update check failed: {e}")
            print()

        # 4. Check if we can send a test message to ourselves
        print("4️⃣  Testing message send capability...")
        # Get bot's own chat ID (won't work, but we can try)
        # Instead, check if sendMessage endpoint is accessible
        try:
            # We need a valid chat_id to test, so we'll just verify the endpoint exists
            response = await client.post(
                f"{API_BASE}/sendMessage",
                json={
                    "chat_id": bot['id'],  # Try sending to bot itself (will fail but tests endpoint)
                    "text": "Test"
                }
            )
            result = response.json()

            if result.get('ok'):
                print("✅ sendMessage endpoint working")
            else:
                error_desc = result.get('description', '')
                if 'bot can\'t initiate conversation' in error_desc.lower() or 'chat not found' in error_desc.lower():
                    print("✅ sendMessage endpoint working (expected error for bot self-message)")
                else:
                    print(f"⚠️  sendMessage error: {error_desc}")
        except Exception as e:
            print(f"❌ sendMessage test failed: {e}")

    print()
    print("=" * 80)
    print("💡 Diagnosis:")
    print()
    print("If webhook URL is set:")
    print("  - Bot is in webhook mode, needs a web server running")
    print("  - Check Railway service logs for startup errors")
    print()
    print("If webhook URL is empty:")
    print("  - Bot should be in polling mode (long polling)")
    print("  - Check if bot process is running on Railway")
    print()
    print("Next steps:")
    print("  1. Check Railway logs: railway logs")
    print("  2. Verify TELEGRAM_BOT_TOKEN on Railway")
    print("  3. Check bot startup script (start_telegram_bot.py)")
    print("  4. Ensure no webhook is interfering")


if __name__ == "__main__":
    asyncio.run(main())
