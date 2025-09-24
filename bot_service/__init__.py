"""
Enhanced Telegram Bot Service
Production-ready bot with advanced search, explanations, and user management
"""

from .advanced_bot import AdvancedRSSBot
from .formatters import MessageFormatter
from .commands import CommandHandler
from .quality_ux import QualityUXHandler

__version__ = "2.0.0"
__all__ = [
    "AdvancedRSSBot",
    "MessageFormatter",
    "CommandHandler",
    "QualityUXHandler"
]