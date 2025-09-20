"""
CLI Integration for LlamaIndex RSS System
=========================================

Integrates LlamaIndex orchestrator with existing main.py CLI
Provides new commands and maintains backward compatibility
"""

import argparse
import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

# Defer heavy imports to runtime to avoid ImportError when
# LlamaIndex optional dependencies are not installed.
try:
    from llamaindex_components import (
        LegacyModeManager as _LegacyModeManager,
        PerformanceMonitor as _PerformanceMonitor,
        CostTracker as _CostTracker,
    )
except Exception:
    _LegacyModeManager = None  # type: ignore
    _PerformanceMonitor = None  # type: ignore
    _CostTracker = None  # type: ignore
from pg_client_new import PgClient

logger = logging.getLogger(__name__)


class LlamaIndexCLI:
    """
    CLI interface for LlamaIndex RSS integration

    Commands:
    - llamaindex-ingest: Process articles with LlamaIndex
    - llamaindex-query: Query with different presets
    - llamaindex-migrate: Migrate existing data
    - llamaindex-monitor: Performance monitoring
    - llamaindex-legacy: Legacy mode management
    """

    def __init__(self):
        self.orchestrator = None
        # Fallback lightweight shims if components unavailable at import time
        if _LegacyModeManager is None:
            class _LegacyShim:
                def is_legacy_enabled(self, _component: str) -> bool:
                    return False
                def set_legacy_mode(self, *_args, **_kwargs) -> None:
                    pass
                def get_status(self) -> Dict[str, Any]:
                    return {
                        'legacy_mode': False,
                        'legacy_components': {},
                        'llamaindex_components': {}
                    }
            self.legacy_manager = _LegacyShim()
        else:
            self.legacy_manager = _LegacyModeManager()

        if _PerformanceMonitor is None:
            class _PerfShim:
                def start_timer(self, _name: str) -> str:
                    return "t"
                def end_timer(self, _timer_id: str) -> float:
                    return 0.0
                def get_stats(self, _name: str) -> Dict[str, Any]:
                    return {'count': 0, 'mean': 0.0}
            self.performance_monitor = _PerfShim()
        else:
            self.performance_monitor = _PerformanceMonitor()

        if _CostTracker is None:
            class _CostShim:
                def add_cost(self, *_args, **_kwargs):
                    pass
            self.cost_tracker = _CostShim()
        else:
            self.cost_tracker = _CostTracker()

    def setup_orchestrator(self) -> bool:
        """Initialize LlamaIndex orchestrator with environment variables"""

        try:
            required_env_vars = {
                'PG_DSN': os.getenv('PG_DSN'),
                'PINECONE_API_KEY': os.getenv('PINECONE_API_KEY'),
                'PINECONE_INDEX': os.getenv('PINECONE_INDEX'),
                'OPENAI_API_KEY': os.getenv('OPENAI_API_KEY'),
                'GEMINI_API_KEY': os.getenv('GEMINI_API_KEY'),
            }

            missing_vars = [var for var, value in required_env_vars.items() if not value]
            if missing_vars:
                print(f"❌ Missing environment variables: {', '.join(missing_vars)}")
                print("Please set them in .env file or environment")
                return False

            # Lazy import to avoid module import at CLI wiring time
            from llamaindex_production import RSSLlamaIndexOrchestrator
            self.orchestrator = RSSLlamaIndexOrchestrator(
                pg_dsn=required_env_vars['PG_DSN'],
                pinecone_api_key=required_env_vars['PINECONE_API_KEY'],
                pinecone_index=required_env_vars['PINECONE_INDEX'],
                openai_api_key=required_env_vars['OPENAI_API_KEY'],
                gemini_api_key=required_env_vars['GEMINI_API_KEY'],
                pinecone_environment=os.getenv('PINECONE_REGION', 'us-east-1-aws')
            )

            print("✅ LlamaIndex orchestrator initialized")
            return True

        except Exception as e:
            print(f"❌ Failed to initialize LlamaIndex orchestrator: {e}")
            logger.exception("Orchestrator initialization failed")
            return False

    async def cmd_llamaindex_ingest(self, args) -> int:
        """Process articles with LlamaIndex pipeline"""

        if not self.setup_orchestrator():
            return 1

        # Check legacy mode
        if self.legacy_manager.is_legacy_enabled('chunking'):
            print("⚠️ Legacy chunking mode enabled - using existing Stage 6")
            print("Run 'python main.py llamaindex-legacy disable' to use LlamaIndex")
            return self._run_legacy_chunking(args)

        try:
            # Get database client
            client = PgClient()

            # Fetch articles ready for processing
            if hasattr(args, 'article_ids') and args.article_ids:
                # Process specific articles
                articles = []
                for article_id in args.article_ids:
                    article = client.get_article_by_id(article_id)
                    if article:
                        articles.append(article)
            else:
                # Process articles ready for chunking
                articles = client.get_articles_ready_for_chunking(limit=args.limit)

            if not articles:
                print("No articles ready for LlamaIndex processing")
                return 0

            print(f"🔄 Processing {len(articles)} articles with LlamaIndex...")

            # Process articles
            total_nodes = 0
            successful = 0
            failed = 0

            for i, article in enumerate(articles, 1):
                try:
                    timer_id = self.performance_monitor.start_timer("llamaindex_ingest")

                    # Process article
                    node_ids = await self.orchestrator.ingest_article(article)

                    duration = self.performance_monitor.end_timer(timer_id)
                    total_nodes += len(node_ids)
                    successful += 1

                    # Mark as processed in database
                    client.mark_llamaindex_processed(
                        article['article_id'],
                        article.get('processing_version', 1),
                        len(node_ids)
                    )

                    if i % 10 == 0:
                        print(f"  Processed {i}/{len(articles)} articles...")

                except Exception as e:
                    failed += 1
                    logger.error(f"Failed to process article {article.get('article_id')}: {e}")

            # Print results
            print(f"✅ LlamaIndex ingestion complete:")
            print(f"  Articles processed: {successful}")
            print(f"  Total nodes created: {total_nodes}")
            print(f"  Failed: {failed}")

            # Performance stats
            ingest_stats = self.performance_monitor.get_stats("llamaindex_ingest_duration")
            if ingest_stats['count'] > 0:
                print(f"  Avg processing time: {ingest_stats['mean']:.2f}s per article")

            client.close()
            return 0

        except Exception as e:
            print(f"❌ LlamaIndex ingestion failed: {e}")
            logger.exception("LlamaIndex ingestion failed")
            return 1

    async def cmd_llamaindex_query(self, args) -> int:
        """Query using LlamaIndex with different presets"""

        if not self.setup_orchestrator():
            return 1

        # Check legacy mode
        if self.legacy_manager.is_legacy_enabled('retrieval'):
            print("⚠️ Legacy retrieval mode enabled - using existing Stage 8")
            return self._run_legacy_query(args)

        try:
            # Parse preset (lazy import enums)
            from llamaindex_production import OutputPreset, LanguageRoute
            preset = OutputPreset(args.preset) if hasattr(args, 'preset') else OutputPreset.QA

            # Parse language
            language = None
            if hasattr(args, 'language') and args.language:
                language = LanguageRoute(args.language)

            print(f"🔍 Querying with LlamaIndex...")
            print(f"  Query: {args.query}")
            print(f"  Preset: {preset.value}")
            print(f"  Language: {language.value if language else 'auto-detect'}")
            print(f"  Max sources: {args.max_sources}")

            timer_id = self.performance_monitor.start_timer("llamaindex_query")

            # Execute query
            result = await self.orchestrator.query(
                query=args.query,
                preset=preset,
                language=language,
                max_sources=args.max_sources
            )

            duration = self.performance_monitor.end_timer(timer_id)

            # Display results
            print(f"\n📰 Answer:")
            print(result['answer'])

            print(f"\n📊 Details:")
            metadata = result['metadata']
            print(f"  Processing time: {metadata['processing_time_ms']:.1f}ms")
            print(f"  Sources used: {metadata['nodes_used']}")
            print(f"  Domain diversity: {metadata['domain_diversity']}")
            print(f"  LLM provider: {metadata['llm_provider']}")
            print(f"  Cost estimate: ${metadata['cost_estimate'].get('total_cost', 0):.4f}")

            print(f"\n📖 Sources:")
            for i, source in enumerate(result['sources'], 1):
                print(f"  [{i}] {source['title']}")
                print(f"      {source['source_domain']} | {source['published_at']}")
                print(f"      {source['url']}")
                if args.verbose:
                    print(f"      Score: {source['relevance_score']:.3f}")
                    print(f"      Preview: {source['text_preview']}")
                print()

            return 0

        except Exception as e:
            print(f"❌ LlamaIndex query failed: {e}")
            logger.exception("LlamaIndex query failed")
            return 1

    async def cmd_llamaindex_migrate(self, args) -> int:
        """Migrate existing data to LlamaIndex format"""

        if not self.setup_orchestrator():
            return 1

        try:
            client = PgClient()

            print(f"🔄 Starting LlamaIndex migration...")

            # Strategy based on args
            if args.strategy == 'fresh':
                # Process only new articles
                articles = client.get_articles_ready_for_chunking(limit=args.limit)
                print(f"Fresh migration: {len(articles)} new articles")

            elif args.strategy == 'backfill':
                # Backfill recent articles (hot namespace)
                cutoff_date = datetime.now() - timedelta(days=30)
                articles = client.get_articles_since_date(cutoff_date, limit=args.limit)
                print(f"Backfill migration: {len(articles)} recent articles")

            elif args.strategy == 'archive':
                # Migrate older articles (archive namespace)
                cutoff_date = datetime.now() - timedelta(days=30)
                articles = client.get_articles_before_date(cutoff_date, limit=args.limit)
                print(f"Archive migration: {len(articles)} older articles")

            else:
                print(f"❌ Unknown migration strategy: {args.strategy}")
                return 1

            # Migration with progress tracking
            migrated = 0
            failed = 0
            batch_size = 10

            for i in range(0, len(articles), batch_size):
                batch = articles[i:i + batch_size]

                # Process batch
                batch_tasks = [
                    self.orchestrator.ingest_article(article)
                    for article in batch
                ]

                try:
                    batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)

                    for j, result in enumerate(batch_results):
                        if isinstance(result, Exception):
                            failed += 1
                            logger.error(f"Migration failed for article {batch[j].get('article_id')}: {result}")
                        else:
                            migrated += 1

                    print(f"  Migrated: {migrated}, Failed: {failed}, Progress: {min(i + batch_size, len(articles))}/{len(articles)}")

                except Exception as e:
                    failed += batch_size
                    logger.error(f"Batch migration failed: {e}")

            print(f"✅ Migration complete:")
            print(f"  Successfully migrated: {migrated}")
            print(f"  Failed: {failed}")
            print(f"  Success rate: {migrated / (migrated + failed) * 100:.1f}%")

            client.close()
            return 0

        except Exception as e:
            print(f"❌ Migration failed: {e}")
            logger.exception("Migration failed")
            return 1

    def cmd_llamaindex_monitor(self, args) -> int:
        """Display performance monitoring and statistics"""

        try:
            print("📊 LlamaIndex Performance Monitor")
            print("=" * 50)

            # Performance stats
            print("\n🚀 Performance Metrics:")
            for metric_name in ['llamaindex_ingest_duration', 'llamaindex_query_duration']:
                stats = self.performance_monitor.get_stats(metric_name)
                if stats['count'] > 0:
                    print(f"  {metric_name}:")
                    print(f"    Requests: {stats['count']}")
                    print(f"    Mean: {stats['mean']:.3f}s")
                    print(f"    P95: {stats['p95']:.3f}s")
                    print(f"    Min/Max: {stats['min']:.3f}s / {stats['max']:.3f}s")

            # Cost tracking
            print("\n💰 Cost Tracking:")
            usage_stats = self.cost_tracker.get_usage_stats()
            print(f"  Today's total cost: ${usage_stats['today_total']:.4f}")

            for provider, remaining in usage_stats['budget_remaining'].items():
                if remaining < float('inf'):
                    print(f"  {provider.title()} budget remaining: ${remaining:.2f}")

            # Legacy mode status
            print("\n🔄 System Status:")
            legacy_status = self.legacy_manager.get_legacy_status()
            if legacy_status['legacy_mode']:
                print("  ⚠️ Legacy mode enabled for:")
                for component, enabled in legacy_status['legacy_components'].items():
                    if enabled:
                        print(f"    - {component}")
            else:
                print("  ✅ Full LlamaIndex mode active")

            # Cache stats (if available)
            if hasattr(self.orchestrator, 'query_cache'):
                print("\n🗄️ Query Cache:")
                cache_stats = self.orchestrator.query_cache.get_stats()
                print(f"  Size: {cache_stats['size']}/{cache_stats['max_size']}")
                print(f"  TTL: {cache_stats['ttl_seconds']}s")
                print(f"  Expired entries: {cache_stats['expired_entries']}")

            return 0

        except Exception as e:
            print(f"❌ Monitoring failed: {e}")
            logger.exception("Monitoring failed")
            return 1

    def cmd_llamaindex_legacy(self, args) -> int:
        """Manage legacy mode and fallbacks"""

        try:
            if args.action == 'enable':
                components = args.components if hasattr(args, 'components') else ['full']
                self.legacy_manager.enable_legacy_mode(components)
                print(f"✅ Legacy mode enabled for: {', '.join(components)}")

            elif args.action == 'disable':
                self.legacy_manager.disable_legacy_mode()
                print("✅ Legacy mode disabled - using full LlamaIndex pipeline")

            elif args.action == 'status':
                status = self.legacy_manager.get_legacy_status()
                print("🔄 Legacy Mode Status:")
                print(f"  Enabled: {status['legacy_mode']}")

                if status['legacy_mode']:
                    print("  Legacy components:")
                    for component, enabled in status['legacy_components'].items():
                        print(f"    {component}: {'✅' if enabled else '❌'}")

                print("  LlamaIndex components:")
                for component, enabled in status['llamaindex_components'].items():
                    print(f"    {component}: {'✅' if enabled else '❌'}")

            else:
                print(f"❌ Unknown legacy action: {args.action}")
                return 1

            return 0

        except Exception as e:
            print(f"❌ Legacy mode management failed: {e}")
            logger.exception("Legacy mode management failed")
            return 1

    def _run_legacy_chunking(self, args) -> int:
        """Fallback to legacy chunking system"""
        print("🔄 Running legacy chunking (Stage 6)...")
        # Import and run existing chunking logic
        # This would call the existing main.py chunk command
        return 0

    def _run_legacy_query(self, args) -> int:
        """Fallback to legacy query system"""
        print("🔄 Running legacy query (Stage 8)...")
        # Import and run existing RAG logic
        # This would call the existing main.py rag command
        return 0


def add_llamaindex_commands(subparsers):
    """Add LlamaIndex commands to main.py argument parser"""

    # LlamaIndex ingestion
    p_ingest = subparsers.add_parser(
        "llamaindex-ingest",
        help="Process articles with LlamaIndex pipeline"
    )
    p_ingest.add_argument("--limit", type=int, default=100, help="Max articles to process")
    p_ingest.add_argument("--article-ids", nargs='+', type=int, help="Process specific article IDs")

    # LlamaIndex query
    p_query = subparsers.add_parser(
        "llamaindex-query",
        help="Query using LlamaIndex with different presets"
    )
    p_query.add_argument("query", help="Search query")
    p_query.add_argument("--preset", choices=['qa', 'digest', 'shorts', 'ideas'], default='qa',
                        help="Output format preset")
    p_query.add_argument("--language", choices=['en', 'ru'], help="Force language route")
    p_query.add_argument("--max-sources", type=int, default=10, help="Maximum sources in response")
    p_query.add_argument("--verbose", action="store_true", help="Show detailed source information")

    # LlamaIndex migration
    p_migrate = subparsers.add_parser(
        "llamaindex-migrate",
        help="Migrate existing data to LlamaIndex format"
    )
    p_migrate.add_argument("strategy", choices=['fresh', 'backfill', 'archive'],
                          help="Migration strategy")
    p_migrate.add_argument("--limit", type=int, default=1000, help="Max articles to migrate")

    # LlamaIndex monitoring
    subparsers.add_parser(
        "llamaindex-monitor",
        help="Display performance monitoring and statistics"
    )

    # LlamaIndex legacy mode
    p_legacy = subparsers.add_parser(
        "llamaindex-legacy",
        help="Manage legacy mode and fallbacks"
    )
    p_legacy.add_argument("action", choices=['enable', 'disable', 'status'],
                         help="Legacy mode action")
    p_legacy.add_argument("--components", nargs='+',
                         choices=['chunking', 'retrieval', 'synthesis', 'full'],
                         default=['full'],
                         help="Components to enable legacy mode for")


async def handle_llamaindex_commands(args) -> int:
    """Handle LlamaIndex-specific commands"""

    cli = LlamaIndexCLI()

    if args.cmd == "llamaindex-ingest":
        return await cli.cmd_llamaindex_ingest(args)
    elif args.cmd == "llamaindex-query":
        return await cli.cmd_llamaindex_query(args)
    elif args.cmd == "llamaindex-migrate":
        return await cli.cmd_llamaindex_migrate(args)
    elif args.cmd == "llamaindex-monitor":
        return cli.cmd_llamaindex_monitor(args)
    elif args.cmd == "llamaindex-legacy":
        return cli.cmd_llamaindex_legacy(args)
    else:
        print(f"❌ Unknown LlamaIndex command: {args.cmd}")
        return 1


# Example usage for testing
if __name__ == "__main__":
    import sys

    # Simple test runner
    class Args:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    async def test_query():
        args = Args(
            cmd="llamaindex-query",
            query="What are the latest AI developments?",
            preset="qa",
            language=None,
            max_sources=8,
            verbose=True
        )

        result = await handle_llamaindex_commands(args)
        print(f"Query test result: {result}")

    # Run test
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        asyncio.run(test_query())
    else:
        print("LlamaIndex CLI integration ready for main.py")
        print("Use 'python llamaindex_cli.py test' to run a simple test")
