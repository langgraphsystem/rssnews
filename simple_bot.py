#!/usr/bin/env python3
"""
Simple Working Bot - Minimal polling bot for testing
"""

import os
import sys
import asyncio
import logging
import httpx
import json
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('simple_bot.log')
    ]
)
logger = logging.getLogger(__name__)

class SimpleTelegramBot:
    def __init__(self, token: str):
        self.token = token
        self.api_url = f"https://api.telegram.org/bot{token}"
        self.offset = 0
        self.running = False

    async def get_me(self):
        """Test bot connection"""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(f"{self.api_url}/getMe")

            if response.status_code == 200:
                return response.json()['result']
            else:
                logger.error(f"getMe failed: {response.status_code}")
                return None

        except Exception as e:
            logger.error(f"getMe error: {e}")
            return None

    async def send_message(self, chat_id: int, text: str):
        """Send message to chat"""
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(
                    f"{self.api_url}/sendMessage",
                    json={
                        'chat_id': chat_id,
                        'text': text,
                        'parse_mode': 'HTML'
                    }
                )

            if response.status_code == 200:
                logger.info(f"✅ Message sent to {chat_id}")
                return True
            else:
                logger.error(f"❌ Send failed: {response.status_code} - {response.text}")
                return False

        except Exception as e:
            logger.error(f"❌ Send error: {e}")
            return False

    async def get_updates(self):
        """Get updates from Telegram"""
        try:
            params = {
                'offset': self.offset,
                'limit': 10,
                'timeout': 30
            }

            async with httpx.AsyncClient(timeout=35) as client:
                response = await client.get(f"{self.api_url}/getUpdates", params=params)

            if response.status_code == 200:
                data = response.json()
                if data['ok']:
                    return data['result']
                else:
                    logger.error(f"API error: {data}")
                    return []
            else:
                logger.error(f"HTTP error: {response.status_code}")
                return []

        except Exception as e:
            logger.error(f"Get updates error: {e}")
            return []

    async def handle_message(self, message):
        """Handle incoming message"""
        chat_id = message['chat']['id']
        user_name = message['from'].get('first_name', 'User')
        text = message.get('text', '')

        logger.info(f"📨 Message from {user_name}: '{text}'")

        # Simple responses
        if text.startswith('/start'):
            response = f"🤖 Привет, {user_name}! Я работаю!\\n\\n📋 Команды:\\n/help - помощь\\n/time - время\\n/echo [текст] - повтор"

        elif text.startswith('/help'):
            response = """📖 <b>Помощь по боту</b>

🔍 <b>Основные команды:</b>
• /start - приветствие
• /help - эта справка
• /time - текущее время
• /echo [текст] - повторить текст
• /status - статус бота

✨ <b>Просто отправь любое сообщение!</b>"""

        elif text.startswith('/time'):
            response = f"🕐 Время: {datetime.now().strftime('%H:%M:%S %d.%m.%Y')}"

        elif text.startswith('/echo '):
            echo_text = text[6:]  # Remove "/echo "
            response = f"🔄 Повторяю: {echo_text}"

        elif text.startswith('/status'):
            response = f"✅ Бот работает!\\n🕐 {datetime.now().strftime('%H:%M:%S')}\\n👤 Отвечаю {user_name}"

        else:
            # Echo any other message
            response = f"👋 {user_name}, ты написал: \"{text}\"\\n\\n💡 Попробуй /help для списка команд"

        # Send response
        await self.send_message(chat_id, response)

    async def run(self):
        """Main bot loop"""
        logger.info("🚀 Запуск простого бота...")

        # Test connection
        bot_info = await self.get_me()
        if not bot_info:
            logger.error("❌ Не удалось подключиться к боту")
            return

        logger.info(f"✅ Бот подключен: @{bot_info['username']}")
        logger.info(f"💬 Отправьте сообщение @{bot_info['username']}")

        self.running = True
        message_count = 0

        while self.running:
            try:
                updates = await self.get_updates()

                for update in updates:
                    # Update offset
                    self.offset = update['update_id'] + 1

                    if 'message' in update:
                        message_count += 1
                        logger.info(f"🔄 Обработка сообщения #{message_count}")
                        await self.handle_message(update['message'])

                if not updates:
                    # No updates, small delay
                    await asyncio.sleep(1)

            except KeyboardInterrupt:
                logger.info("⏹️ Получен сигнал остановки")
                break
            except Exception as e:
                logger.error(f"💥 Ошибка в главном цикле: {e}")
                await asyncio.sleep(5)

        self.running = False
        logger.info(f"🏁 Бот остановлен. Обработано сообщений: {message_count}")

def main():
    # Check environment
    token = os.getenv('TELEGRAM_BOT_TOKEN')

    if not token:
        print("❌ TELEGRAM_BOT_TOKEN не установлен в окружении")
        print("💡 Установите переменную окружения TELEGRAM_BOT_TOKEN (Railway env)")
        return 1

    print("🤖 ПРОСТОЙ ТЕСТОВЫЙ БОТ")
    print("=" * 40)
    print(f"🔑 Токен: {'✅ установлен' if token else '❌ отсутствует'}")
    print("💬 Отправь сообщение боту для теста!")
    print("⏹️  Ctrl+C для остановки")
    print()

    # Run bot
    bot = SimpleTelegramBot(token)

    try:
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        print("\\n⏹️ Остановлено пользователем")
        return 0

if __name__ == "__main__":
    main()
