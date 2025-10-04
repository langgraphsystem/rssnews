#!/usr/bin/env python3
"""
Get your Telegram chat ID
Run this, then send any message to the bot to see your chat ID
"""
import os
import httpx
import asyncio
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
if not TELEGRAM_BOT_TOKEN:
    print("❌ TELEGRAM_BOT_TOKEN not set")
    exit(1)

API_BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


async def main():
    print("🔍 Getting recent Telegram updates...")
    print("📱 Send any message to the bot to see your chat ID")
    print()

    async with httpx.AsyncClient() as client:
        # Get bot info
        response = await client.get(f"{API_BASE}/getMe")
        bot_info = response.json()
        if bot_info.get('ok'):
            bot = bot_info['result']
            print(f"✅ Bot: @{bot['username']}")
            print()

        # Get updates
        response = await client.get(f"{API_BASE}/getUpdates?limit=10")
        result = response.json()

        if result.get('ok') and result.get('result'):
            updates = result['result']
            print(f"📬 Found {len(updates)} recent updates")
            print()

            seen_chats = set()
            for update in updates:
                if 'message' in update:
                    msg = update['message']
                    chat = msg.get('chat', {})
                    chat_id = chat.get('id')
                    chat_type = chat.get('type')
                    username = chat.get('username', 'N/A')

                    if chat_id and chat_id not in seen_chats:
                        seen_chats.add(chat_id)
                        print(f"Chat ID: {chat_id}")
                        print(f"  Type: {chat_type}")
                        print(f"  Username: @{username}")
                        print(f"  Use this in .env: TEST_CHAT_ID={chat_id}")
                        print()

            if not seen_chats:
                print("❌ No messages found")
                print("💡 Send a message to the bot first, then run this script again")
        else:
            print("❌ Failed to get updates")
            print(result)


if __name__ == "__main__":
    asyncio.run(main())
