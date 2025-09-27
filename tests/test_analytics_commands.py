#!/usr/bin/env python3
"""
Lightweight test for Analytics commands (/trends, /quality).
Stubs DB and RankingAPI, overrides network sends to capture outputs.
"""

import asyncio
import os
import sys
from typing import Any, Dict, List

# Ensure repo root on path for package imports
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Import formatter and bot
from bot_service.formatters import MessageFormatter
from bot_service.advanced_bot import AdvancedRSSBot


class FakeDB:
    def get_search_analytics(self, days: int = 1) -> Dict[str, Any]:
        return {
            "method_stats": [
                {"method": "hybrid", "total": 120, "unique_users": 45},
                {"method": "fts", "total": 35, "unique_users": 20},
                {"method": "semantic", "total": 18, "unique_users": 12},
            ],
            "top_queries": [
                {"query": "ai regulation", "frequency": 14},
                {"query": "crypto market", "frequency": 11},
                {"query": "green energy", "frequency": 9},
            ],
            "performance": {"avg_response_time_ms": 210},
        }


class FakeRankingAPI:
    def __init__(self) -> None:
        self._formatter = MessageFormatter()
        self._db = FakeDB()

    def get_system_health(self) -> Dict[str, Any]:
        return {
            "timestamp": "2025-09-25T12:00:00Z",
            "system_status": "healthy",
            "search_analytics": self._db.get_search_analytics(days=1),
            "quality_trend": {
                "ndcg_at_10": 0.72,
                "precision_at_10": 0.61,
                "avg_response_time_ms": 230,
                "total_queries": 173,
            },
            "top_domains": [
                {"domain": "reuters.com", "source_score": 0.93},
                {"domain": "techcrunch.com", "source_score": 0.88},
                {"domain": "nature.com", "source_score": 0.85},
            ],
            "current_weights": {
                "semantic": 0.58,
                "fts": 0.32,
                "freshness": 0.06,
                "source": 0.04,
            },
            "cache_stats": {"hits": 120, "misses": 22},
        }


class TestBot(AdvancedRSSBot):
    """Subclass that avoids real DB/HTTP and captures messages."""

    def __init__(self):
        # Bypass parent init to avoid DB/HTTP setup
        self.bot_token = "TEST_TOKEN"
        self.api_base = "https://api.telegram.org/botTEST"
        self.gpt5 = None
        self.formatter = MessageFormatter()
        self.ranking_api = FakeRankingAPI()
        self.db = FakeDB()
        self._outbox: List[Dict[str, Any]] = []

    async def _send_message(self, chat_id: str, text: str, reply_markup: Dict = None, parse_mode: str = "Markdown") -> bool:
        self._outbox.append({"chat_id": chat_id, "text": text, "reply_markup": reply_markup, "parse_mode": parse_mode})
        return True

    async def _send_long_message(self, chat_id: str, text: str, reply_markup: Dict = None, parse_mode: str = "Markdown") -> bool:
        # Simulate splitting, but just capture once for test simplicity
        return await self._send_message(chat_id, text, reply_markup, parse_mode)

    def _create_inline_keyboard(self, buttons: List[List[Dict[str, Any]]]) -> Dict[str, Any]:
        return {"inline_keyboard": buttons}


async def run():
    bot = TestBot()
    chat_id = "123"
    user_id = "u1"

    # /trends
    await bot.handle_trends_command(chat_id, user_id)
    # /quality
    await bot.handle_quality_command(chat_id, user_id)

    # Return captured outputs
    return bot._outbox


if __name__ == "__main__":
    messages = asyncio.run(run())
    print("==== Captured Messages ====")
    for i, msg in enumerate(messages, 1):
        print(f"\n[{i}] chat_id={msg['chat_id']}")
        print(msg["text"])  # show body
        if msg.get("reply_markup"):
            print(f"Buttons: {msg['reply_markup']}")
        if msg.get("parse_mode"):
            print(f"ParseMode: {msg['parse_mode']}")
