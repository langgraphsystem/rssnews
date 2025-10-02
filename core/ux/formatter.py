"""
UX Formatter — Telegram-friendly formatting for Phase 1 responses
Converts BaseAnalysisResponse to readable Telegram messages with buttons
"""

import logging
from typing import Dict, Any, List
from schemas.analysis_schemas import BaseAnalysisResponse, ErrorResponse

logger = logging.getLogger(__name__)


def format_for_telegram(response: BaseAnalysisResponse | ErrorResponse) -> Dict[str, Any]:
    """
    Format response for Telegram

    Args:
        response: BaseAnalysisResponse or ErrorResponse

    Returns:
        Dict with 'text' and optional 'buttons'
    """
    if isinstance(response, ErrorResponse):
        return _format_error_response(response)
    else:
        return _format_success_response(response)


def _format_success_response(response: BaseAnalysisResponse) -> Dict[str, Any]:
    """Format successful analysis response"""

    lines = []

    # Header with emoji
    header = response.header
    emoji = _get_emoji_for_command(header)
    lines.append(f"{emoji} **{header}**\n")

    # TL;DR
    lines.append(f"📊 **Краткий обзор:**")
    lines.append(f"{response.tldr}\n")

    # Insights (with emojis based on type)
    if response.insights:
        lines.append(f"💡 **Ключевые выводы:**")
        for i, insight in enumerate(response.insights[:5], 1):
            emoji = _get_insight_emoji(insight.type)
            text = insight.text
            lines.append(f"{emoji} {text}")
        lines.append("")

    # Evidence block (compact)
    if response.evidence:
        lines.append(f"📰 **Источники ({len(response.evidence)}):**")
        for i, ev in enumerate(response.evidence[:5], 1):
            title = ev.title[:80] + "..." if len(ev.title) > 80 else ev.title
            date = ev.date
            url = ev.url or ""

            if url:
                # Telegram link format
                lines.append(f"{i}. [{title}]({url})")
                lines.append(f"   📅 {date}")
            else:
                lines.append(f"{i}. {title}")
                lines.append(f"   📅 {date}")
        lines.append("")

    # Meta info (compact)
    confidence_emoji = _get_confidence_emoji(response.meta.confidence)
    confidence_pct = int(response.meta.confidence * 100)
    lines.append(f"{confidence_emoji} Уверенность: {confidence_pct}% | Model: {response.meta.model}")

    # Warnings (if any)
    if response.warnings:
        lines.append(f"\n⚠️ Предупреждения: {', '.join(response.warnings[:2])}")

    # Build message
    text = "\n".join(lines)

    # Build buttons (optional)
    buttons = _build_buttons(response)

    return {
        "text": text,
        "buttons": buttons,
        "parse_mode": "Markdown"
    }


def _format_error_response(error_response: ErrorResponse) -> Dict[str, Any]:
    """Format error response"""

    error = error_response.error

    lines = []
    lines.append(f"❌ **Ошибка**\n")
    lines.append(f"{error.user_message}")

    if error.retryable:
        lines.append(f"\n💡 Попробуйте повторить запрос через некоторое время.")

    # Tech details (for debugging)
    if error.tech_message and error.tech_message != error.user_message:
        lines.append(f"\n🔧 Детали: `{error.tech_message[:100]}`")

    text = "\n".join(lines)

    return {
        "text": text,
        "buttons": None,
        "parse_mode": "Markdown"
    }


def _get_emoji_for_command(header: str) -> str:
    """Get emoji based on command/header"""
    header_lower = header.lower()

    if "trend" in header_lower:
        return "📈"
    elif "keyphrase" in header_lower or "keyword" in header_lower:
        return "🔑"
    elif "sentiment" in header_lower:
        return "😊"
    elif "topic" in header_lower:
        return "📚"
    else:
        return "📊"


def _get_insight_emoji(insight_type: str) -> str:
    """Get emoji for insight type"""
    emoji_map = {
        "fact": "✅",
        "hypothesis": "🤔",
        "recommendation": "💡",
        "conflict": "⚠️"
    }
    return emoji_map.get(insight_type, "•")


def _get_confidence_emoji(confidence: float) -> str:
    """Get emoji for confidence level"""
    if confidence >= 0.8:
        return "🟢"
    elif confidence >= 0.6:
        return "🟡"
    else:
        return "🟠"


def _build_buttons(response: BaseAnalysisResponse) -> List[List[Dict[str, str]]]:
    """Build inline buttons for response"""

    buttons = []

    # Row 1: Explain / More Evidence
    row1 = [
        {"text": "📖 Объяснить", "callback_data": f"explain_{response.meta.correlation_id}"},
        {"text": "📰 Все источники", "callback_data": f"sources_{response.meta.correlation_id}"}
    ]
    buttons.append(row1)

    # Row 2: Related / Follow (optional)
    row2 = [
        {"text": "🔗 Похожие", "callback_data": f"related_{response.meta.correlation_id}"},
        {"text": "🔔 Следить", "callback_data": f"follow_{response.meta.correlation_id}"}
    ]
    buttons.append(row2)

    return buttons


def format_result_details(response: BaseAnalysisResponse, detail_type: str = "default") -> str:
    """
    Format additional result details (for detailed views)

    Args:
        response: BaseAnalysisResponse
        detail_type: Type of details to show ("keywords", "sentiment", "topics", etc.)

    Returns:
        Formatted text
    """
    result = response.result

    if detail_type == "keywords" or "keyphrases" in result:
        return _format_keyphrases_detail(result)

    elif detail_type == "sentiment" or "overall" in result:
        return _format_sentiment_detail(result)

    elif detail_type == "topics" or "topics" in result:
        return _format_topics_detail(result)

    else:
        return "Детали недоступны"


def _format_keyphrases_detail(result: Dict[str, Any]) -> str:
    """Format keyphrases in detail"""
    lines = []
    lines.append("🔑 **Ключевые фразы:**\n")

    keyphrases = result.get("keyphrases", [])
    for i, kp in enumerate(keyphrases[:15], 1):
        phrase = kp.get("phrase", "")
        score = kp.get("score", 0.0)
        lang = kp.get("lang", "")

        # Build bar
        bar = "█" * int(score * 10)
        lines.append(f"{i}. **{phrase}** `{bar}` {score:.2f} ({lang})")

    return "\n".join(lines)


def _format_sentiment_detail(result: Dict[str, Any]) -> str:
    """Format sentiment in detail"""
    lines = []
    lines.append("😊 **Анализ настроений:**\n")

    # Overall
    overall = result.get("overall", 0.0)
    sentiment_label = "позитивное" if overall > 0.3 else "негативное" if overall < -0.3 else "нейтральное"
    lines.append(f"Общий тон: **{sentiment_label}** ({overall:+.2f})\n")

    # Emotions
    emotions = result.get("emotions", {})
    if emotions:
        lines.append("**Эмоции:**")
        for emotion, score in sorted(emotions.items(), key=lambda x: x[1], reverse=True):
            if score > 0.1:
                bar = "█" * int(score * 10)
                emoji = _get_emotion_emoji(emotion)
                lines.append(f"{emoji} {emotion.capitalize()}: `{bar}` {score:.2f}")
        lines.append("")

    # Aspects
    aspects = result.get("aspects", [])
    if aspects:
        lines.append("**Аспекты:**")
        for aspect in aspects[:5]:
            name = aspect.get("name", "")
            score = aspect.get("score", 0.0)
            lines.append(f"• {name}: {score:+.2f}")

    return "\n".join(lines)


def _format_topics_detail(result: Dict[str, Any]) -> str:
    """Format topics in detail"""
    lines = []
    lines.append("📚 **Выявленные темы:**\n")

    topics = result.get("topics", [])
    for i, topic in enumerate(topics[:8], 1):
        label = topic.get("label", "")
        size = topic.get("size", 0)
        trend = topic.get("trend", "stable")
        terms = topic.get("terms", [])

        # Trend emoji
        trend_emoji = {"rising": "📈", "falling": "📉", "stable": "➡️"}.get(trend, "➡️")

        lines.append(f"**{i}. {label}** {trend_emoji}")
        lines.append(f"   📊 {size} статей | Ключевые термины: {', '.join(terms[:5])}")
        lines.append("")

    # Emerging topics
    emerging = result.get("emerging", [])
    if emerging:
        lines.append("🌟 **Развивающиеся темы:**")
        for em in emerging[:3]:
            lines.append(f"• {em}")
        lines.append("")

    # Gaps
    gaps = result.get("gaps", [])
    if gaps:
        lines.append("🔍 **Недостаточно освещённые темы:**")
        for gap in gaps[:2]:
            lines.append(f"• {gap}")

    return "\n".join(lines)


def _get_emotion_emoji(emotion: str) -> str:
    """Get emoji for emotion"""
    emoji_map = {
        "joy": "😊",
        "fear": "😨",
        "anger": "😠",
        "sadness": "😢",
        "surprise": "😲"
    }
    return emoji_map.get(emotion.lower(), "😐")