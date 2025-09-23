"""
Comprehensive RSS News System Statistics Reporter
Collects stats from feeds -> processing -> embeddings -> bot integration
"""

import os
import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List
import logging

# Load environment from .env file
from dotenv import load_dotenv
load_dotenv()

from pg_client_new import PgClient
from services.service_manager import ServiceManager
from local_llm_chunker import LocalLLMChunker
from local_embedding_generator import LocalEmbeddingGenerator

logger = logging.getLogger(__name__)

class SystemStatsReporter:
    """Comprehensive system statistics reporter"""

    def __init__(self):
        self.db = PgClient()
        self.service_manager = ServiceManager()
        self.llm = LocalLLMChunker()

    def collect_feed_stats(self) -> Dict[str, Any]:
        """Collect RSS feed statistics"""
        try:
            with self.db._cursor() as cur:
                # Check if feeds table exists and get stats
                cur.execute("SELECT COUNT(*) FROM feeds")
                total_feeds = cur.fetchone()[0]

                # Top domains from articles
                cur.execute("""
                    SELECT
                        source as domain,
                        COUNT(*) as count
                    FROM articles_index
                    WHERE source IS NOT NULL
                    GROUP BY source
                    ORDER BY count DESC
                    LIMIT 5
                """)
                top_sources = cur.fetchall()

                return {
                    'total_feeds': total_feeds,
                    'active_feeds': total_feeds,  # Assume all are active
                    'healthy_feeds': total_feeds,
                    'top_sources': [{'domain': s[0], 'count': s[1]} for s in top_sources]
                }
        except Exception as e:
            logger.error(f"Failed to collect feed stats: {e}")
            return {'error': str(e)}

    def collect_article_stats(self) -> Dict[str, Any]:
        """Collect article processing statistics"""
        try:
            with self.db._cursor() as cur:
                # Total articles
                cur.execute("SELECT COUNT(*) FROM articles_index")
                total_articles = cur.fetchone()[0]

                # Recent articles (last 24h)
                cur.execute("""
                    SELECT COUNT(*)
                    FROM articles_index
                    WHERE first_seen > NOW() - INTERVAL '24 hours'
                """)
                recent_articles = cur.fetchone()[0]

                # Articles by status
                cur.execute("""
                    SELECT
                        ready_for_chunking,
                        COUNT(*) as count
                    FROM articles_index
                    GROUP BY ready_for_chunking
                """)
                status_counts = {str(bool(row[0])): row[1] for row in cur.fetchall()}

                # Top sources
                cur.execute("""
                    SELECT
                        source,
                        COUNT(*) as count
                    FROM articles_index
                    WHERE first_seen > NOW() - INTERVAL '7 days'
                    AND source IS NOT NULL
                    GROUP BY source
                    ORDER BY count DESC
                    LIMIT 5
                """)
                top_sources = cur.fetchall()

                return {
                    'total_articles': total_articles,
                    'recent_24h': recent_articles,
                    'status_counts': status_counts,
                    'top_sources': [{'domain': s[0], 'count': s[1]} for s in top_sources]
                }
        except Exception as e:
            logger.error(f"Failed to collect article stats: {e}")
            return {'error': str(e)}

    def collect_chunk_stats(self) -> Dict[str, Any]:
        """Collect chunk processing statistics"""
        try:
            with self.db._cursor() as cur:
                # Total chunks
                cur.execute("SELECT COUNT(*) FROM article_chunks")
                total_chunks = cur.fetchone()[0]

                # Chunks by processing stage
                cur.execute("""
                    SELECT
                        CASE
                            WHEN fts_vector IS NULL THEN 'needs_fts'
                            WHEN embedding IS NULL THEN 'needs_embedding'
                            ELSE 'complete'
                        END as stage,
                        COUNT(*) as count
                    FROM article_chunks
                    GROUP BY stage
                """)
                processing_stages = {row[0]: row[1] for row in cur.fetchall()}

                # Recent chunks
                cur.execute("""
                    SELECT COUNT(*)
                    FROM article_chunks
                    WHERE created_at > NOW() - INTERVAL '24 hours'
                """)
                recent_chunks = cur.fetchone()[0]

                # Average chunks per article
                cur.execute("""
                    SELECT AVG(chunk_count)
                    FROM (
                        SELECT article_id, COUNT(*) as chunk_count
                        FROM article_chunks
                        GROUP BY article_id
                    ) t
                """)
                avg_chunks = cur.fetchone()[0] or 0

                return {
                    'total_chunks': total_chunks,
                    'recent_24h': recent_chunks,
                    'processing_stages': processing_stages,
                    'avg_chunks_per_article': round(float(avg_chunks), 2)
                }
        except Exception as e:
            logger.error(f"Failed to collect chunk stats: {e}")
            return {'error': str(e)}

    def collect_embedding_stats(self) -> Dict[str, Any]:
        """Collect embedding statistics"""
        try:
            with self.db._cursor() as cur:
                # Embedding counts
                cur.execute("SELECT COUNT(*) FROM article_chunks WHERE embedding IS NOT NULL")
                embedded_chunks = cur.fetchone()[0]

                cur.execute("SELECT COUNT(*) FROM article_chunks WHERE embedding IS NULL")
                pending_embeddings = cur.fetchone()[0]

                # Recent embeddings
                cur.execute("""
                    SELECT COUNT(*)
                    FROM article_chunks
                    WHERE embedding IS NOT NULL
                    AND created_at > NOW() - INTERVAL '24 hours'
                """)
                recent_embeddings = cur.fetchone()[0]

                # Vector dimensions (check sample)
                cur.execute("""
                    SELECT embedding
                    FROM article_chunks
                    WHERE embedding IS NOT NULL
                    LIMIT 1
                """)
                sample_embedding = cur.fetchone()
                vector_dimensions = 0
                if sample_embedding and sample_embedding[0]:
                    # For pgvector, this should be 3072
                    vector_dimensions = 3072  # Known from our setup

                return {
                    'embedded_chunks': embedded_chunks,
                    'pending_embeddings': pending_embeddings,
                    'recent_24h': recent_embeddings,
                    'vector_dimensions': vector_dimensions,
                    'completion_rate': round((embedded_chunks / (embedded_chunks + pending_embeddings)) * 100, 2) if (embedded_chunks + pending_embeddings) > 0 else 0
                }
        except Exception as e:
            logger.error(f"Failed to collect embedding stats: {e}")
            return {'error': str(e)}

    async def collect_service_stats(self) -> Dict[str, Any]:
        """Collect service health statistics"""
        try:
            # Get service status
            status = await self.service_manager.get_service_status()

            # Test LLM connectivity
            llm_status = True
            try:
                import httpx
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.post(
                        'http://localhost:11434/api/generate',
                        json={'model': 'qwen2.5-coder:3b', 'prompt': 'Hello', 'stream': False}
                    )
                    llm_status = response.status_code == 200
            except:
                llm_status = False

            return {
                'service_manager_running': status.get('service_manager_running', False),
                'services': status.get('services', {}),
                'llm_connectivity': llm_status
            }
        except Exception as e:
            logger.error(f"Failed to collect service stats: {e}")
            return {'error': str(e)}

    async def generate_llm_insights(self, stats: Dict[str, Any]) -> str:
        """Generate GPT-5 powered insights from statistics"""
        try:
            prompt = f"""Проанализируй только эту статистику и ответь:

1. Какие главные проблемы ты видишь.
2. Какие метрики указывают на наибольшую критичность.
3. Что делать в первую очередь, чтобы исправить ситуацию.
4. Какие рекомендации для поддержания стабильности и предотвращения таких проблем в будущем.

СТАТИСТИКА RSS СИСТЕМЫ:
FEEDS: {stats.get('feeds', {})}
ARTICLES: {stats.get('articles', {})}
CHUNKS: {stats.get('chunks', {})}
EMBEDDINGS: {stats.get('embeddings', {})}
SERVICES: {stats.get('services', {})}

Ответь кратко и по делу."""

            # Use GPT-5 Responses API
            from gpt5_service_new import GPT5Service

            service = GPT5Service()
            response = service.send(
                message=prompt,
                model_id="gpt-5-mini",  # Cost-effective for analysis
                reasoning_effort="minimal",  # Fast analysis
                preset="deterministic"  # Uses low verbosity
            )

            return response.strip() if response else "GPT-5 анализ недоступен"

        except Exception as e:
            logger.error(f"Failed to generate GPT-5 insights: {e}")
            return f"GPT-5 анализ недоступен: {str(e)}"

    async def collect_full_report(self) -> Dict[str, Any]:
        """Collect comprehensive system report"""
        print("🔍 Collecting RSS News System Statistics...")

        # Collect all statistics
        stats = {
            'timestamp': datetime.now().isoformat(),
            'feeds': self.collect_feed_stats(),
            'articles': self.collect_article_stats(),
            'chunks': self.collect_chunk_stats(),
            'embeddings': self.collect_embedding_stats(),
            'services': await self.collect_service_stats()
        }

        # Generate LLM insights
        print("🤖 Generating LLM insights...")
        stats['llm_insights'] = await self.generate_llm_insights(stats)

        return stats

    def format_report_for_bot(self, stats: Dict[str, Any]) -> str:
        """Format statistics for bot message"""
        feeds = stats.get('feeds', {})
        articles = stats.get('articles', {})
        chunks = stats.get('chunks', {})
        embeddings = stats.get('embeddings', {})
        services = stats.get('services', {})

        report = f"""🤖 **RSS News System Report**
📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}

📡 **FEEDS**
• Active: {feeds.get('active_feeds', 0)}/{feeds.get('total_feeds', 0)}
• Healthy (24h): {feeds.get('healthy_feeds', 0)}

📰 **ARTICLES**
• Total: {articles.get('total_articles', 0):,}
• Recent (24h): {articles.get('recent_24h', 0)}

🧩 **CHUNKS**
• Total: {chunks.get('total_chunks', 0):,}
• Recent (24h): {chunks.get('recent_24h', 0)}
• Avg per article: {chunks.get('avg_chunks_per_article', 0)}

🧠 **EMBEDDINGS**
• Completed: {embeddings.get('embedded_chunks', 0):,}
• Pending: {embeddings.get('pending_embeddings', 0):,}
• Completion: {embeddings.get('completion_rate', 0)}%
• Dimensions: {embeddings.get('vector_dimensions', 0)}

⚙️ **SERVICES**
• Manager: {'🟢' if services.get('service_manager_running') else '🔴'}
• LLM: {'🟢' if services.get('llm_connectivity') else '🔴'}

🤖 **AI INSIGHTS**
{stats.get('llm_insights', 'No insights available')}
"""
        return report

    async def send_to_telegram(self, message: str):
        """Send report to Telegram bot"""
        bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        chat_id = os.getenv('TELEGRAM_CHAT_ID')

        if not bot_token or not chat_id:
            print("⚠️ Telegram credentials not set (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)")
            print("📱 Message Preview:")
            print("=" * 50)
            print(message)
            print("=" * 50)

            # Save to file as fallback
            with open('bot_report.txt', 'w', encoding='utf-8') as f:
                f.write(message)
            print("💾 Report saved to bot_report.txt")
            return False

        try:
            import httpx

            # Split message if too long (Telegram limit ~4096 chars)
            max_length = 4000
            if len(message) > max_length:
                # Split into parts
                parts = []
                current_part = ""
                lines = message.split('\n')

                for line in lines:
                    if len(current_part + line + '\n') > max_length:
                        if current_part:
                            parts.append(current_part.strip())
                        current_part = line + '\n'
                    else:
                        current_part += line + '\n'

                if current_part:
                    parts.append(current_part.strip())
            else:
                parts = [message]

            # Send message parts
            success_count = 0
            async with httpx.AsyncClient(timeout=30.0) as client:
                for i, part in enumerate(parts):
                    if len(parts) > 1:
                        part = f"📊 **Part {i+1}/{len(parts)}**\n\n{part}"

                    response = await client.post(
                        f'https://api.telegram.org/bot{bot_token}/sendMessage',
                        json={
                            'chat_id': chat_id,
                            'text': part,
                            'parse_mode': 'Markdown',
                            'disable_web_page_preview': True
                        }
                    )

                    if response.status_code == 200:
                        success_count += 1
                        print(f"✅ Telegram message part {i+1} sent successfully")
                    else:
                        print(f"❌ Failed to send Telegram message part {i+1}: {response.status_code}")
                        print(f"Response: {response.text}")

            if success_count == len(parts):
                print(f"🎉 All {len(parts)} message parts sent to Telegram successfully!")
                return True
            else:
                print(f"⚠️ Only {success_count}/{len(parts)} parts sent successfully")
                return False

        except Exception as e:
            print(f"❌ Error sending to Telegram: {e}")

            # Save to file as fallback
            with open('bot_report.txt', 'w', encoding='utf-8') as f:
                f.write(message)
            print("💾 Report saved to bot_report.txt as fallback")
            return False

async def main():
    """Main execution function"""
    logging.basicConfig(level=logging.INFO)

    try:
        reporter = SystemStatsReporter()

        # Collect full report
        stats = await reporter.collect_full_report()

        # Format for bot
        bot_message = reporter.format_report_for_bot(stats)

        # Send to Telegram
        await reporter.send_to_telegram(bot_message)

        # Also save detailed JSON
        with open('system_stats.json', 'w', encoding='utf-8') as f:
            json.dump(stats, f, indent=2, ensure_ascii=False)
        print("💾 Detailed stats saved to system_stats.json")

    except Exception as e:
        print(f"❌ Error generating report: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())