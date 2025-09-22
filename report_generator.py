"""
System report generator for RSS news aggregation system
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import requests
import json
import asyncio
from html import escape as _html_escape

logger = logging.getLogger(__name__)


def generate_report(client, period_hours: int = 8, format: str = "html") -> str:
    """Generate comprehensive system report"""

    # Calculate time period
    now = datetime.now()
    period_start = now - timedelta(hours=period_hours)

    # Collect statistics
    stats = collect_statistics(client, period_start, now)

    # Format report
    if format == "html":
        return format_html_report(stats, period_hours)
    else:
        return format_markdown_report(stats, period_hours)


async def generate_enhanced_telegram_report(client, period_hours: int = 8) -> str:
    """Generate base report for Telegram (GPT analysis removed)."""
    now = datetime.now()
    period_start = now - timedelta(hours=period_hours)
    stats = collect_statistics(client, period_start, now)
    base_report_md = format_markdown_report(stats, period_hours)
    return f"<pre>{_html_escape(base_report_md)}</pre>"


def collect_statistics(client, period_start: datetime, period_end: datetime) -> Dict[str, Any]:
    """Collect all system statistics"""

    stats = {
        'timestamp': period_end.isoformat(),
        'period_hours': (period_end - period_start).total_seconds() / 3600,
        'feeds': {},
        'raw_articles': {},
        'stage6': {},
        'stage7': {}
    }

    try:
        with client._cursor() as cur:
            # Feed statistics
            cur.execute("SELECT COUNT(*) FROM feeds WHERE status = 'active'")
            stats['feeds']['active'] = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM feeds")
            stats['feeds']['total'] = cur.fetchone()[0]

            # Raw articles by status
            cur.execute("""
                SELECT status, COUNT(*)
                FROM raw
                WHERE status IS NOT NULL
                GROUP BY status
            """)
            for status, count in cur.fetchall():
                stats['raw_articles'][status] = count

            # Articles in period
            cur.execute("""
                SELECT status, COUNT(*)
                FROM raw
                WHERE created_at >= %s AND created_at <= %s
                GROUP BY status
            """, (period_start, period_end))

            period_stats = {}
            for status, count in cur.fetchall():
                period_stats[status] = count
            stats['raw_articles']['period'] = period_stats

            # Stage 6 statistics
            cur.execute("SELECT COUNT(*) FROM articles_index WHERE COALESCE(ready_for_chunking, false) = true")
            stats['stage6']['ready_for_chunking'] = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM articles_index WHERE COALESCE(chunking_completed, false) = true")
            stats['stage6']['chunking_completed'] = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM article_chunks")
            stats['stage6']['total_chunks'] = cur.fetchone()[0]

            # New chunks in period
            cur.execute("""
                SELECT COUNT(*) FROM article_chunks
                WHERE created_at >= %s AND created_at <= %s
            """, (period_start, period_end))
            stats['stage6']['new_chunks_period'] = cur.fetchone()[0]

            # Stage 7 statistics
            cur.execute("SELECT COUNT(*) FROM article_chunks WHERE fts_vector IS NOT NULL")
            stats['stage7']['fts_indexed'] = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM article_chunks WHERE embedding IS NOT NULL")
            stats['stage7']['embeddings_stored'] = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM article_chunks WHERE fts_vector IS NULL")
            stats['stage7']['fts_missing'] = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM article_chunks WHERE embedding IS NULL")
            stats['stage7']['embeddings_missing'] = cur.fetchone()[0]

    except Exception as e:
        logger.error(f"Database statistics collection failed: {e}")
        stats['error'] = str(e)

    # Pinecone statistics removed

    return stats


# collect_pinecone_stats removed


def format_markdown_report(stats: Dict[str, Any], period_hours: int) -> str:
    """Format report as Markdown"""

    report_time = datetime.fromisoformat(stats['timestamp']).strftime('%Y-%m-%d %H:%M:%S')

    # Calculate totals
    total_articles = sum(stats['raw_articles'].get(status, 0)
                        for status in ['stored', 'partial', 'duplicate', 'pending', 'processing', 'error'])

    period_total = sum(stats['raw_articles'].get('period', {}).values())

    # Processing rates
    chunks_total = stats['stage6']['total_chunks']
    fts_coverage = (stats['stage7']['fts_indexed'] / max(chunks_total, 1)) * 100
    emb_coverage = (stats['stage7']['embeddings_stored'] / max(chunks_total, 1)) * 100

    report = f"""🤖 **RSS News System Report**
📅 {report_time} (Period: {period_hours}h)

**📊 Feeds Status**
• Active: {stats['feeds']['active']}/{stats['feeds']['total']}

**📰 Articles Overview**
• Total: {total_articles:,}
• New ({period_hours}h): {period_total:,}

**📈 Processing Status**
• ✅ Stored: {stats['raw_articles'].get('stored', 0):,}
• ⏳ Pending: {stats['raw_articles'].get('pending', 0):,}
• 🔄 Processing: {stats['raw_articles'].get('processing', 0):,}
• 📋 Partial: {stats['raw_articles'].get('partial', 0):,}
• ❌ Errors: {stats['raw_articles'].get('error', 0):,}

**🔧 Stage 6 (Chunking)**
• Ready: {stats['stage6']['ready_for_chunking']:,}
• Completed: {stats['stage6']['chunking_completed']:,}
• Total chunks: {chunks_total:,}
• New chunks ({period_hours}h): {stats['stage6']['new_chunks_period']:,}

**🔍 Stage 7 (Indexing)**
• FTS indexed: {stats['stage7']['fts_indexed']:,}/{chunks_total:,} ({fts_coverage:.1f}%)
• Embeddings: {stats['stage7']['embeddings_stored']:,}/{chunks_total:,} ({emb_coverage:.1f}%)
"""

    # Pinecone section removed in production cleanup

    # Add period breakdown if there's activity
    period_stats = stats['raw_articles'].get('period', {})
    if period_total > 0:
        report += f"\n\n**📊 Period Activity ({period_hours}h)**"
        for status, count in period_stats.items():
            if count > 0:
                report += f"\n• {status}: {count:,}"

    return report


def format_html_report(stats: Dict[str, Any], period_hours: int) -> str:
    """Format report as HTML (safe-escaped, preformatted)."""
    markdown_report = format_markdown_report(stats, period_hours)
    return f"<pre>{_html_escape(markdown_report)}</pre>"


# External GPT analysis removed in production cleanup


def send_telegram_report(report: str, format: str = "html") -> None:
    """Send report to Telegram"""

    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')

    if not bot_token or not chat_id:
        raise ValueError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set")

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    # Prepare payload
    payload = {
        'chat_id': chat_id,
        'text': report,
        'parse_mode': 'HTML' if format == 'html' else 'Markdown',
        'disable_web_page_preview': True
    }

    # Truncate if too long (Telegram limit is 4096 chars)
    if len(report) > 4000:
        report = report[:3900] + "\n\n... (truncated)"
        payload['text'] = report

    # Send request
    response = requests.post(url, json=payload, timeout=30)

    if response.status_code != 200:
        raise Exception(f"Telegram API error: {response.status_code} - {response.text}")

    result = response.json()
    if not result.get('ok'):
        raise Exception(f"Telegram API error: {result.get('description', 'Unknown error')}")

    logger.info("Report sent to Telegram successfully")


async def send_enhanced_telegram_report(client, period_hours: int = 8) -> None:
    """Generate and send base report to Telegram (without GPT analysis)."""

    try:
        # Generate base report (HTML-safe)
        report = await generate_enhanced_telegram_report(client, period_hours)

        # Send to Telegram as HTML
        send_telegram_report(report, format="html")

        logger.info("Report sent to Telegram successfully")

    except Exception as e:
        logger.error(f"Failed to send enhanced Telegram report: {e}")
        raise
