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

logger = logging.getLogger(__name__)


def generate_report(client, period_hours: int = 8, format: str = "markdown") -> str:
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
    """Generate enhanced report with GPT analysis for Telegram"""

    # Calculate time period
    now = datetime.now()
    period_start = now - timedelta(hours=period_hours)

    # Collect statistics
    stats = collect_statistics(client, period_start, now)

    # Generate base report
    base_report = format_markdown_report(stats, period_hours)

    # Add GPT analysis
    gpt_analysis = await generate_gpt5_analysis(stats, period_hours)

    # Combine reports
    enhanced_report = f"{base_report}\n\n{gpt_analysis}"

    return enhanced_report


def collect_statistics(client, period_start: datetime, period_end: datetime) -> Dict[str, Any]:
    """Collect all system statistics"""

    stats = {
        'timestamp': period_end.isoformat(),
        'period_hours': (period_end - period_start).total_seconds() / 3600,
        'feeds': {},
        'raw_articles': {},
        'stage6': {},
        'stage7': {},
        'pinecone': {}
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

    # Pinecone statistics
    try:
        stats['pinecone'] = collect_pinecone_stats()
    except Exception as e:
        logger.warning(f"Pinecone statistics collection failed: {e}")
        stats['pinecone'] = {'error': str(e)}

    return stats


def collect_pinecone_stats() -> Dict[str, Any]:
    """Collect Pinecone index statistics"""

    pinecone_stats = {}

    try:
        # Check if Pinecone is configured
        api_key = os.getenv('PINECONE_API_KEY')
        index_name = os.getenv('PINECONE_INDEX')
        region = os.getenv('PINECONE_REGION', 'us-east-1-aws')

        if not api_key or not index_name:
            return {'status': 'not_configured'}

        # Try to get Pinecone stats using REST API
        host = f"{index_name}-{region}.svc.{region}.pinecone.io"
        url = f"https://{host}/describe_index_stats"

        headers = {
            'Api-Key': api_key,
            'Content-Type': 'application/json'
        }

        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code == 200:
            data = response.json()
            pinecone_stats = {
                'status': 'connected',
                'total_vector_count': data.get('totalVectorCount', 0),
                'dimension': data.get('dimension', 0),
                'index_fullness': data.get('indexFullness', 0),
                'namespaces': data.get('namespaces', {})
            }
        else:
            pinecone_stats = {
                'status': 'error',
                'error': f"HTTP {response.status_code}: {response.text[:200]}"
            }

    except requests.RequestException as e:
        pinecone_stats = {
            'status': 'connection_error',
            'error': str(e)
        }
    except Exception as e:
        pinecone_stats = {
            'status': 'error',
            'error': str(e)
        }

    return pinecone_stats


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

    # Pinecone section
    pc_stats = stats['pinecone']
    if pc_stats.get('status') == 'connected':
        report += f"""
**🌲 Pinecone Status**
• Vectors: {pc_stats.get('total_vector_count', 0):,}
• Dimension: {pc_stats.get('dimension', 0)}
• Fullness: {(pc_stats.get('index_fullness', 0) * 100):.1f}%"""
    elif pc_stats.get('status') == 'not_configured':
        report += "\n**🌲 Pinecone**: Not configured"
    else:
        report += f"\n**🌲 Pinecone**: ❌ {pc_stats.get('error', 'Unknown error')[:50]}"

    # Add period breakdown if there's activity
    period_stats = stats['raw_articles'].get('period', {})
    if period_total > 0:
        report += f"\n\n**📊 Period Activity ({period_hours}h)**"
        for status, count in period_stats.items():
            if count > 0:
                report += f"\n• {status}: {count:,}"

    return report


def format_html_report(stats: Dict[str, Any], period_hours: int) -> str:
    """Format report as HTML"""

    # Convert markdown to basic HTML
    markdown_report = format_markdown_report(stats, period_hours)

    # Simple markdown to HTML conversion
    html_report = markdown_report.replace('**', '<b>').replace('**', '</b>')
    html_report = html_report.replace('• ', '• ')
    html_report = html_report.replace('\n', '<br>\n')

    return f"<pre>{html_report}</pre>"


async def generate_gpt5_analysis(stats: Dict[str, Any], period_hours: int) -> str:
    """Generate GPT-5 analysis of RSS system statistics in Russian"""

    try:
        # Check if OpenAI API key is available
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            return "⚠️ *GPT-5 анализ недоступен:* OPENAI_API_KEY не настроен"

        # Import OpenAI client
        try:
            from openai import AsyncOpenAI
        except ImportError:
            return "⚠️ *GPT-5 анализ недоступен:* openai библиотека не установлена"

        # Prepare statistics summary for analysis
        total_articles = sum(stats['raw_articles'].get(status, 0)
                           for status in ['stored', 'partial', 'duplicate', 'pending', 'processing', 'error'])
        period_total = sum(stats['raw_articles'].get('period', {}).values())

        # Calculate key metrics
        success_rate = (stats['raw_articles'].get('stored', 0) / max(total_articles, 1)) * 100
        error_rate = (stats['raw_articles'].get('error', 0) / max(total_articles, 1)) * 100
        fts_coverage = (stats['stage7']['fts_indexed'] / max(stats['stage6']['total_chunks'], 1)) * 100

        # Create analysis prompt
        analysis_prompt = f"""
Ты - аналитик RSS новостной системы. Проанализируй статистику работы системы за {period_hours} часов и дай краткий анализ на русском языке.

Статистика:
- Активных фидов: {stats['feeds']['active']}/{stats['feeds']['total']}
- Всего статей: {total_articles:,}
- Новых статей за период: {period_total}
- Успешно сохранено: {stats['raw_articles'].get('stored', 0)} ({success_rate:.1f}%)
- Ошибок: {stats['raw_articles'].get('error', 0)} ({error_rate:.1f}%)
- В очереди: {stats['raw_articles'].get('pending', 0)}
- Готово к чанкингу: {stats['stage6']['ready_for_chunking']}
- Завершено чанков: {stats['stage6']['chunking_completed']}
- Всего чанков: {stats['stage6']['total_chunks']}
- FTS индексация: {stats['stage7']['fts_indexed']}/{stats['stage6']['total_chunks']} ({fts_coverage:.1f}%)
- Embeddings: {stats['stage7']['embeddings_stored']}

Дай краткий анализ (2-3 предложения):
1. Общее состояние системы
2. Основные проблемы или достижения
3. Рекомендации по улучшению

Отвечай коротко и по делу, используй эмодзи для наглядности.
"""

        client = AsyncOpenAI(api_key=api_key)

        # GPT-5 использует Responses API
        system_prompt = "Ты - опытный аналитик IT-систем, специализирующийся на RSS агрегаторах и обработке новостей."

        response = await client.responses.create(
            model="gpt-5",
            instructions=system_prompt,
            input=analysis_prompt,
            max_output_tokens=500
        )

        # Извлекаем текст из Responses API (используем тот же подход что в main.py)
        analysis = getattr(response, "output_text", None)
        if not analysis:
            try:
                # Fallback к структуре .output[0].content[0].text
                parts = []
                output = getattr(response, "output", None) or []
                for item in output:
                    for content in getattr(item, "content", []) or []:
                        text = getattr(content, "text", None)
                        if text:
                            parts.append(text)
                analysis = "\n".join(parts)
            except Exception:
                analysis = None

        if not analysis:
            analysis = "Анализ завершен, но текст не удалось извлечь"

        return f"🤖 **GPT-5 Анализ:**\n{analysis.strip()}"

    except Exception as e:
        logger.error(f"GPT-5 analysis failed: {e}")
        return f"⚠️ *GPT анализ недоступен:* {str(e)[:100]}"


def send_telegram_report(report: str, format: str = "markdown") -> None:
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
        'parse_mode': 'Markdown' if format == 'markdown' else 'HTML',
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
    """Generate and send enhanced report with GPT analysis to Telegram"""

    try:
        # Generate enhanced report with GPT analysis
        report = await generate_enhanced_telegram_report(client, period_hours)

        # Send to Telegram
        send_telegram_report(report, format="markdown")

        logger.info("Enhanced report with GPT analysis sent to Telegram successfully")

    except Exception as e:
        logger.error(f"Failed to send enhanced Telegram report: {e}")
        raise