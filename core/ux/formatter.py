"""
UX Formatter — Telegram-friendly formatting for Phase 1 responses
Converts BaseAnalysisResponse to readable Telegram messages with buttons
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from schemas.analysis_schemas import BaseAnalysisResponse, ErrorResponse, Evidence, EvidenceRef, Insight

logger = logging.getLogger(__name__)

CENTRAL_TZ = ZoneInfo("America/Chicago")


def format_for_telegram(response: BaseAnalysisResponse | ErrorResponse) -> Dict[str, Any]:
    """Format response for Telegram"""
    if isinstance(response, ErrorResponse):
        return _format_error_response(response)
    return _format_success_response(response)


def _format_success_response(response: BaseAnalysisResponse) -> Dict[str, Any]:
    """Select formatting strategy based on response type"""
    if _is_general_qa_response(response):
        return _format_general_qa_response(response)

    if _is_news_response(response):
        return _format_news_response(response)

    # Fallback to legacy formatting for other commands (/events, /graph, etc.)
    return _format_legacy_success_response(response)


def _is_general_qa_response(response: BaseAnalysisResponse) -> bool:
    result = getattr(response, "result", {})
    if isinstance(result, dict):
        source = result.get("source", "")
        if source:
            return source.upper() == "LLM/KB"
    header = (response.header or "").lower()
    return "answer" in header and not response.evidence


def _is_news_response(response: BaseAnalysisResponse) -> bool:
    header = (response.header or "").lower()
    return "news analysis" in header or "новостной анализ" in header


def _format_general_qa_response(response: BaseAnalysisResponse) -> Dict[str, Any]:
    """Format general knowledge answers (LLM/KB)"""
    result = getattr(response, "result", {}) if isinstance(getattr(response, "result", {}), dict) else {}
    answer = result.get("answer") or response.tldr or ""
    source = result.get("source", "LLM/KB")

    lines = [
        "🤖 **Knowledge Answer**",
        _escape_markdown(answer.strip()),
        "",
        f"Source: {_escape_markdown(source)}",
    ]

    return {
        "text": "\n".join(lines).strip(),
        "buttons": None,
        "parse_mode": "MarkdownV2",
    }


def _format_news_response(response: BaseAnalysisResponse) -> Dict[str, Any]:
    """Format news-mode responses with summary bullets and structured sources"""
    evidence_index = _build_evidence_index(response.evidence)

    summary_entries = _build_summary_entries(response.insights, evidence_index)
    if len(summary_entries) < 3:
        summary_entries = _augment_summary_from_evidence(summary_entries, response.evidence)

    source_entries = _build_source_entries(response.evidence)

    lines: List[str] = []
    lines.append("🧾 **Short Summary**")
    for entry in summary_entries[:5]:
        lines.append(f"• {entry}")

    if not summary_entries:
        lines.append("• No summary available")

    lines.append("")
    lines.append("📰 **Sources (top 5)**")
    if source_entries:
        lines.extend(source_entries[:10])
    else:
        lines.append("• No sources available")

    return {
        "text": "\n".join(lines).strip(),
        "buttons": None,  # Buttons injected later by Phase3 handlers
        "parse_mode": "MarkdownV2",
    }


def _build_summary_entries(insights: List[Insight], evidence_index: Dict[str, Evidence]) -> List[str]:
    entries: List[str] = []
    for insight in insights[:5]:
        summary_text = insight.text.strip()
        date_text = None
        for ref in insight.evidence_refs or []:
            date_text = _format_iso_date(ref.date) or _format_iso_date(_lookup_evidence_date(ref, evidence_index))
            if date_text:
                break
        if not date_text and insight.evidence_refs:
            ref = insight.evidence_refs[0]
            evidence_obj = _lookup_evidence(ref, evidence_index)
            if evidence_obj:
                date_text = _format_iso_date(evidence_obj.date)
        summary = _escape_markdown(summary_text)
        if date_text:
            entries.append(f"{date_text} – {summary}")
        else:
            entries.append(summary)
    return entries


def _augment_summary_from_evidence(existing: List[str], evidence: List[Evidence]) -> List[str]:
    augmented = list(existing)
    for ev in evidence:
        if len(augmented) >= 5:
            break
        title = ev.title or "Untitled"
        date_text = _format_iso_date(ev.date)
        summary = _escape_markdown(title)
        if date_text:
            augmented.append(f"{date_text} – {summary}")
        else:
            augmented.append(summary)
    return augmented


def _build_source_entries(evidence: List[Evidence]) -> List[str]:
    entries: List[str] = []
    for ev in evidence[:5]:
        title = _escape_markdown(ev.title or "Untitled")
        url = ev.url or ""
        date_text = _format_iso_date(ev.date) or "Date unknown"
        domain = _escape_markdown(_extract_domain(url)) if url else "Unknown domain"
        snippet = _escape_markdown(_truncate(ev.snippet or ev.text or "", 160))

        if url:
            entries.append(f"- [{title}]({url}) · {date_text} · {domain}")
        else:
            entries.append(f"- {title} · {date_text} · {domain}")
        if snippet:
            entries.append(f"  {snippet}")
    return entries


def _format_legacy_success_response(response: BaseAnalysisResponse) -> Dict[str, Any]:
    """Original formatting used for non-ask commands"""
    lines = []

    header = response.header
    emoji = _get_emoji_for_command(header)
    lines.append(f"{emoji} **{header}**\n")

    lines.append(f"📊 **Краткий обзор:**")
    lines.append(f"{response.tldr}\n")

    if response.insights:
        lines.append(f"💡 **Ключевые выводы:**")
        for i, insight in enumerate(response.insights[:5], 1):
            emoji_insight = _get_insight_emoji(insight.type)
            text = insight.text
            lines.append(f"{emoji_insight} {text}")
        lines.append("")

    if response.evidence:
        lines.append(f"📰 **Источники ({len(response.evidence)}):**")
        for i, ev in enumerate(response.evidence[:5], 1):
            title = ev.title[:80] + "..." if len(ev.title) > 80 else ev.title
            date = ev.date
            url = ev.url or ""

            if url:
                lines.append(f"{i}. [{title}]({url})")
                lines.append(f"   📅 {date}")
            else:
                lines.append(f"{i}. {title}")
                lines.append(f"   📅 {date}")
        lines.append("")

    confidence_emoji = _get_confidence_emoji(response.meta.confidence)
    confidence_pct = int(response.meta.confidence * 100)
    lines.append(f"{confidence_emoji} Уверенность: {confidence_pct}% | Model: {response.meta.model}")

    if response.warnings:
        lines.append(f"\n⚠️ Предупреждения: {', '.join(response.warnings[:2])}")

    text = "\n".join(lines)
    buttons = _build_buttons(response)

    return {
        "text": text,
        "buttons": buttons,
        "parse_mode": "MarkdownV2"
    }


def _format_error_response(error_response: ErrorResponse) -> Dict[str, Any]:
    """Format error response"""
    error = error_response.error

    lines = []
    lines.append(f"❌ **Ошибка**\n")
    lines.append(f"{error.user_message}")

    if error.retryable:
        lines.append(f"\n💡 Попробуйте повторить запрос через некоторое время.")

    if error.tech_message and error.tech_message != error.user_message:
        lines.append(f"\n🔧 Детали: `{error.tech_message[:100]}`")

    text = "\n".join(lines)

    return {
        "text": text,
        "buttons": None,
        "parse_mode": "MarkdownV2"
    }


def format_result_details(response: BaseAnalysisResponse, *, detail_type: str = "sources") -> str:
    """Produce detailed Markdown text for callbacks (sources/insights/meta).

    This is a lightweight utility used by orchestrator callbacks to render
    additional details on demand. It intentionally avoids buttons and returns
    plain Markdown text.
    """
    try:
        dt = (detail_type or "sources").lower()
        lines: List[str] = []

        if dt in {"insight", "insights"}:
            lines.append("🧩 Insights (detailed)")
            if not response.insights:
                lines.append("• No insights available")
            else:
                for i, ins in enumerate(response.insights, 1):
                    refs = ", ".join(
                        filter(
                            None,
                            [
                                getattr(ref, "date", None)
                                for ref in (ins.evidence_refs or [])
                            ],
                        )
                    )
                    lines.append(f"{i}. {ins.type}: {ins.text}")
                    if refs:
                        lines.append(f"   📅 {refs}")
            return "\n".join(lines)

        if dt in {"meta", "metrics", "details"}:
            m = response.meta
            lines.append("📊 Meta")
            lines.append(f"Model: {m.model} ({m.version})")
            lines.append(f"Confidence: {int(m.confidence*100)}%")
            lines.append(f"Correlation ID: {m.correlation_id}")
            if response.warnings:
                lines.append("")
                lines.append("⚠️ Warnings:")
                for w in response.warnings[:5]:
                    lines.append(f"• {w}")
            return "\n".join(lines)

        # Default: sources
        lines.append("📰 Sources (full)")
        if not response.evidence:
            lines.append("• No sources available")
        else:
            for i, ev in enumerate(response.evidence, 1):
                title = _escape_markdown(ev.title)
                url = ev.url or ""
                date = ev.date or ""
                # Avoid Markdown links to prevent parse errors; print plain URL
                lines.append(f"{i}. {title}")
                if url:
                    lines.append(f"   🔗 {url}")
                if date:
                    lines.append(f"   📅 {date}")
                if ev.snippet:
                    lines.append(f"   🧾 {_escape_markdown(ev.snippet)}")
        return "\n".join(lines)
    except Exception as exc:
        logger.error("format_result_details failed: %s", exc, exc_info=True)
        return "❌ Failed to render details."


def _build_evidence_index(evidence: List[Evidence]) -> Dict[str, Evidence]:
    index: Dict[str, Evidence] = {}
    for ev in evidence:
        key = None
        if ev.article_id:
            key = str(ev.article_id)
        elif ev.url:
            key = ev.url
        if key:
            index[key] = ev
    return index


def _lookup_evidence(ref: EvidenceRef, evidence_index: Dict[str, Evidence]) -> Optional[Evidence]:
    if not ref:
        return None
    if ref.article_id and str(ref.article_id) in evidence_index:
        return evidence_index[str(ref.article_id)]
    if ref.url and ref.url in evidence_index:
        return evidence_index[ref.url]
    return None


def _lookup_evidence_date(ref: EvidenceRef, evidence_index: Dict[str, Evidence]) -> Optional[str]:
    evidence = _lookup_evidence(ref, evidence_index)
    return evidence.date if evidence else None


def _format_iso_date(value: Optional[str]) -> Optional[str]:
    if not value:
        return None

    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if not text:
            return None
        try:
            dt = datetime.fromisoformat(text.replace('Z', '+00:00'))
        except ValueError:
            for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
                try:
                    dt = datetime.strptime(text, fmt)
                    dt = dt.replace(tzinfo=timezone.utc)
                    break
                except ValueError:
                    dt = None
            if dt is None:
                return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    try:
        central = dt.astimezone(CENTRAL_TZ)
    except Exception as exc:  # pragma: no cover - fallback for unexpected tz errors
        logger.debug(f"Failed to convert date '{value}' to America/Chicago: {exc}")
        central = dt

    return central.isoformat(timespec='seconds')


def _extract_domain(url: str) -> str:
    if not url:
        return ""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path
        return domain.lstrip('www.')
    except Exception:
        return url


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _escape_markdown(text: str) -> str:
    if not text:
        return ""
    replacements = {
        '\\': '\\\\',
        '`': '\\`',
        '*': '\\*',
        '_': '\\_',
        '[': '\\[',
        ']': '\\]',
        '(': '\\(',
        ')': '\\)',
    }
    result = text
    for target, replacement in replacements.items():
        result = result.replace(target, replacement)
    return result


def _get_emoji_for_command(header: str) -> str:
    header_lower = (header or "").lower()
    if "trend" in header_lower:
        return "📈"
    if "keyphrase" in header_lower or "keyword" in header_lower:
        return "🔑"
    if "sentiment" in header_lower:
        return "😊"
    if "topic" in header_lower:
        return "📚"
    return "📊"


def _get_insight_emoji(insight_type: str) -> str:
    emoji_map = {
        "fact": "✅",
        "hypothesis": "🤔",
        "recommendation": "💡",
        "conflict": "⚠️",
    }
    return emoji_map.get(insight_type, "•")


def _get_confidence_emoji(confidence: float) -> str:
    if confidence >= 0.8:
        return "🟢"
    if confidence >= 0.6:
        return "🟡"
    return "🟠"


def _build_buttons(response: BaseAnalysisResponse) -> List[List[Dict[str, str]]]:
    buttons = []
    row1 = [
        {"text": "📖 Объяснить", "callback_data": f"explain_{response.meta.correlation_id}"},
        {"text": "📰 Все источники", "callback_data": f"sources_{response.meta.correlation_id}"},
    ]
    buttons.append(row1)

    row2 = [
        {"text": "🔗 Похожие", "callback_data": f"related_{response.meta.correlation_id}"},
        {"text": "🔔 Следить", "callback_data": f"follow_{response.meta.correlation_id}"},
    ]
    buttons.append(row2)

    return buttons
