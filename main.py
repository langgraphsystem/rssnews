"""
Main CLI for RSS news aggregation system
"""

import argparse
import logging
import os
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from pg_client_new import PgClient
from rss.poller import RSSPoller
from worker import ArticleWorker, process_pending
from net.http import HttpClient
from discovery import ensure_feed

def _init_logging():
    """Initialize logging after ensuring logs directory exists"""
    os.makedirs('logs', exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('logs/rssnews.log', encoding='utf-8')
        ]
    )

_init_logging()

logger = logging.getLogger(__name__)


def main():
    
    if not os.getenv("PG_DSN"):
        print("Error: PG_DSN environment variable not set.")
        return 1
        
    ap = argparse.ArgumentParser("RSS News Aggregation System")
    sub = ap.add_subparsers(dest="cmd", required=True)

    # Database schema command
    sub.add_parser("ensure", help="Create/verify database schema")

    # Feed discovery command
    p_dis = sub.add_parser("discovery", help="Add RSS feeds to the system")
    p_dis.add_argument(
        "--feed", action="append", help="RSS URL. Can specify multiple.", default=[]
    )
    p_dis.add_argument(
        "--lang", help="Language code (e.g. en, ru)", default=None
    )
    p_dis.add_argument(
        "--category", help="Feed category", default=None
    )

    # Polling command
    p_poll = sub.add_parser("poll", help="Poll active RSS feeds and queue new articles")
    p_poll.add_argument(
        "--limit", type=int, help="Limit number of feeds to poll", default=None
    )
    p_poll.add_argument(
        "--batch-size", type=int, help="Batch size for processing", default=10
    )
    p_poll.add_argument(
        "--workers", type=int, help="Number of concurrent workers", default=10
    )

    # Worker command
    p_work = sub.add_parser("work", help="Process pending articles (parse and extract content)")
    p_work.add_argument(
        "--batch-size", type=int, help="Batch size for processing", default=50
    )
    p_work.add_argument(
        "--workers", type=int, help="Number of concurrent workers", default=10
    )
    p_work.add_argument(
        "--worker-id", help="Worker identifier", default="worker-1"
    )
    p_work.add_argument(
        "--simplified", action="store_true", help="Use simplified worker (no chunking/FTS/embeddings)"
    )

    # Retry queue management
    p_flush = sub.add_parser("flush-queue", help="Process retry queue")
    p_flush.add_argument(
        "--limit", type=int, help="Max items to process from retry queue", default=10
    )
    # Backward compatibility alias (deprecated)
    p_flush.add_argument(
        "--max-retries", type=int, help="[Deprecated] Use --limit instead", default=None
    )

    # Statistics command
    p_stats = sub.add_parser("stats", help="Show system statistics")
    p_stats.add_argument(
        "--detailed", action="store_true", help="Show detailed statistics"
    )


    # Stage 7 indexing command
    p_index = sub.add_parser("index", help="Stage 7: update FTS and embeddings")
    p_index.add_argument("--limit", type=int, default=128, help="Limit of chunks to index")

    # Stage 8 RAG command
    p_rag = sub.add_parser("rag", help="Stage 8: answer questions using RAG")
    p_rag.add_argument("query", help="Question to answer")
    p_rag.add_argument("--limit", type=int, default=10, help="Number of chunks to retrieve")
    p_rag.add_argument("--alpha", type=float, default=0.5, help="Weight for hybrid search (0=embedding, 1=FTS)")
    # Optional constrained FTS filters
    p_rag.add_argument("--must", help="Required terms (space-separated). Builds AND tsquery with :*", default=None)
    p_rag.add_argument("--any", help="Optional terms (space-separated). Builds OR tsquery with :*", default=None)
    p_rag.add_argument("--source", action="append", help="Limit to source domains (repeatable)")
    p_rag.add_argument("--since-days", type=int, default=None, help="Limit to articles newer than N days")
    p_rag.add_argument("--answer", action="store_true", help="Generate LLM answer over top results")
    p_rag.add_argument("--answer-lang", default="ru", help="Answer language (ru/en)")
    p_rag.add_argument("--max-context", type=int, default=6000, help="Max characters of context for LLM")

    # DB inspect command
    p_db = sub.add_parser("db-inspect", help="Inspect database: summary, tables, schema, samples")
    p_db.add_argument("--tables", action="store_true", help="List public tables")
    p_db.add_argument("--schema", help="Show schema for a table (public.<name> or <name>)")
    p_db.add_argument("--sample", type=int, default=None, help="Show last N rows per core table")
    p_db.add_argument("--summary", action="store_true", help="Show summary stats (default if no flags)")

    # Services command
    p_services = sub.add_parser("services", help="Manage processing services (chunking, FTS, embeddings)")
    p_services.add_argument("action", choices=["start", "run-once", "status"], help="Service action")
    p_services.add_argument(
        "--services", nargs="*", choices=["chunking", "fts", "embedding"],
        help="Specific services to run (for run-once)"
    )
    p_services.add_argument(
        "--chunking-interval", type=int, default=30, help="Chunking service interval"
    )
    p_services.add_argument(
        "--fts-interval", type=int, default=60, help="FTS service interval"
    )
    p_services.add_argument(
        "--embedding-interval", type=int, default=45, help="Embedding service interval"
    )
    # New: batch size controls with validation ranges
    p_services.add_argument(
        "--chunking-batch", type=int, default=None,
        help="Chunking batch size (min 10, max 100)"
    )
    p_services.add_argument(
        "--embedding-batch", type=int, default=None,
        help="Embedding batch size (min 20, max 5000)"
    )
    p_services.add_argument(
        "--fts-batch", type=int, default=None,
        help="FTS batch size (min 100, max 200000)"
    )

    # Report command
    p_report = sub.add_parser("report", help="Generate and send system report")
    p_report.add_argument("--send-telegram", action="store_true", help="Send report to Telegram")
    p_report.add_argument("--period-hours", type=int, default=8, help="Report period in hours (default: 8)")
    p_report.add_argument("--format", choices=["markdown", "html"], default="html", help="Report format (default: html)")

    # LlamaIndex commands removed - using only local LLM chunking

    args = ap.parse_args()
    
    # Initialize database client
    logger.info("Initializing database connection")
    client = PgClient()
    
    try:
        if args.cmd == "ensure":
            logger.info("Ensuring database schema")
            client.ensure_schema()
            print("✓ Database schema ensured")
            return

        if args.cmd == "discovery":
            if not args.feed:
                print("Error: Please specify at least one --feed <rss_url>")
                return
                
            logger.info(f"Adding {len(args.feed)} feeds")
            for feed_url in args.feed:
                try:
                    feed_id = client.insert_feed(feed_url, args.lang, args.category)
                    if feed_id:
                        print(f"✓ Added feed: {feed_url}")
                    else:
                        print(f"~ Feed already exists: {feed_url}")
                except Exception as e:
                    print(f"✗ Failed to add feed {feed_url}: {e}")
                    
            print("✓ Discovery finished")
            return

        if args.cmd == "poll":
            logger.info("Starting RSS polling")
            poller = RSSPoller(
                client, 
                batch_size=args.batch_size, 
                max_workers=args.workers
            )
            
            try:
                stats = poller.poll_active_feeds(args.limit)
                
                print(f"✓ Polling complete:")
                print(f"  Feeds processed: {stats['feeds_polled']}")
                print(f"  Successful: {stats['feeds_successful']}")
                print(f"  Cached (not modified): {stats['feeds_cached']}")
                print(f"  New articles: {stats['new_articles']}")
                print(f"  Errors: {stats['feeds_errors']}")
                
                if stats['errors']:
                    print("\nErrors:")
                    for error in stats['errors'][:5]:  # Show first 5 errors
                        print(f"  - {error['url']}: {error['error']}")
                        
            finally:
                poller.close()
            return

        if args.cmd == "work":
            logger.info("Starting article processing")

            if args.simplified:
                # Use simplified worker without chunking/FTS/embeddings
                from worker_simplified import SimplifiedArticleWorker
                worker = SimplifiedArticleWorker(
                    client,
                    batch_size=args.batch_size,
                    max_workers=args.workers
                )
                print("Using simplified worker (no chunking/FTS/embeddings)")
            else:
                # Use full worker with chunking/FTS/embeddings
                worker = ArticleWorker(
                    client,
                    batch_size=args.batch_size,
                    max_workers=args.workers
                )
                print("Using full worker (with chunking/FTS/embeddings)")

            try:
                stats = worker.process_pending_articles()

                print(f"✓ Processing complete:")
                print(f"  Articles processed: {stats['articles_processed']}")
                print(f"  Successful: {stats['successful']}")
                print(f"  Duplicates: {stats['duplicates']}")
                print(f"  Partial: {stats['partial']}")
                print(f"  Errors: {stats['errors']}")

                if stats['error_details']:
                    print("\nErrors:")
                    for error in stats['error_details'][:5]:  # Show first 5 errors
                        print(f"  - {error['url']}: {error['error']}")

            finally:
                worker.close()
            return

        if args.cmd == "flush-queue":
            logger.info("Processing retry queue")
            limit = args.limit if getattr(args, 'limit', None) is not None else 10
            # Allow deprecated alias to override if provided
            if getattr(args, 'max_retries', None) is not None:
                limit = args.max_retries
            http_client = HttpClient()
            try:
                processed = http_client.process_retry_queue(limit=limit)
                print(f"✓ Processed {processed} items from retry queue")
            finally:
                http_client.close()
            return

        if args.cmd == "stats":
            logger.info("Generating statistics")
            stats = client.get_stats()
            
            print("=== RSS News System Statistics ===")
            print(f"Active feeds: {stats.get('active_feeds', 0)}")
            print(f"Total articles: {stats.get('total_articles', 0)}")
            print(f"Articles (last 24h): {stats.get('articles_24h', 0)}")
            
            if stats.get('articles'):
                print("\nArticles by status:")
                for status, count in stats['articles'].items():
                    print(f"  {status}: {count}")
                    
            if args.detailed:
                # Show additional detailed stats
                print("\n=== Detailed Statistics ===")
                print(f"Database connection: {client.dsn}")
                print(f"Timestamp: {datetime.now().isoformat()}")
            
            return


        if args.cmd == "index":
            logger.info("Starting Stage 7 indexing (FTS + optional embeddings)")
            # Fetch chunks needing indexing (implementation decides the criteria)
            chunks = client.get_chunks_for_indexing(limit=args.limit)
            if not chunks:
                print("No chunks need indexing")
                return
            ids = [c['id'] for c in chunks if 'id' in c]

            # 1) Update FTS vectors (always)
            fts_updated = 0
            try:
                fts_updated = client.update_chunks_fts(ids)
            except Exception as e:
                logger.error(f"FTS update failed: {e}")

            # 2) Embeddings step removed: external APIs disabled; keep only FTS update
            emb_count = 0

            print(f"✓ Indexing complete: fts_updated={fts_updated}, considered={len(ids)}, embeddings_updated={emb_count}")
            return

        if args.cmd == "rag":
            logger.info("Starting Stage 8 RAG retrieval")
            try:
                # If constrained filters provided, prefer constrained FTS path
                constrained = bool(args.must or args.any or args.source or args.since_days)
                if constrained:
                    # Build tsquery string in 'english'
                    def to_terms(s: str) -> list[str]:
                        return [t.strip() for t in s.split() if t.strip()]
                    must = [f"{t}:*" for t in to_terms(args.must or "")]
                    anyt = [f"{t}:*" for t in to_terms(args.any or "")]
                    ts = " & ".join(must) if must else ""
                    if anyt:
                        ts = (ts + (" & " if ts else "")) + "(" + " | ".join(anyt) + ")"
                    if not ts:
                        # Fallback to plainto using normalized query
                        ts = None
                    rows = client.search_chunks_fts_ts(ts, args.query, args.source or [], args.since_days, limit=args.limit * 3)
                    class _Res:
                        def __init__(self, chunks, q):
                            self.chunks = chunks
                            self.query_normalized = q
                            self.search_type = "fts_constrained"
                    res = _Res(rows, args.query)
                else:
                    from stage8_retrieval.retriever import HybridRetriever
                    retriever = HybridRetriever(client)
                    res = retriever.hybrid_retrieve(args.query, limit=args.limit * 3, alpha=args.alpha)
                print("=== RAG Results ===")
                print(f"Query (normalized): {res.query_normalized}")
                print(f"Search type: {res.search_type}")
                
                # Collapse by article (prefer first/highest-ranked)
                seen = set()
                collapsed = []
                for ch in res.chunks:
                    aid = ch.get('article_id') or ch.get('url') or ch.get('id')
                    if not aid:
                        continue
                    if aid in seen:
                        continue
                    seen.add(aid)
                    collapsed.append(ch)
                    if len(collapsed) >= args.limit:
                        break
                
                # Build simple snippets around first matched term
                terms = [t for t in (res.query_normalized or '').split() if t]
                print(f"Results: {len(collapsed)}")
                for i, ch in enumerate(collapsed, 1):
                    title = ch.get('title_norm') or ch.get('title') or ''
                    url = ch.get('url') or ''
                    src = ch.get('source_domain') or ch.get('source') or ''
                    txt = (ch.get('text') or '')
                    snippet = ''
                    if txt:
                        low = txt.lower()
                        pos = -1
                        for t in terms:
                            p = low.find(t.lower())
                            if p != -1:
                                pos = p
                                break
                        if pos == -1:
                            snippet = txt[:160].replace('\n', ' ')
                        else:
                            start = max(0, pos - 80)
                            end = min(len(txt), pos + 80)
                            snippet = ("..." if start > 0 else "") + txt[start:end].replace('\n', ' ') + ("..." if end < len(txt) else "")
                    print(f"[{i}] {title} | {src} | {url}")
                    if snippet:
                        print(f"    ↳ {snippet}")

                # External LLM answer generation removed in production cleanup
            except Exception as e:
                logger.error(f"RAG retrieval failed: {e}")
                print(f"✗ RAG retrieval failed: {e}")
            return

        if args.cmd == "db-inspect":
            # If no explicit flags, default to summary + small samples
            want_default = not (args.tables or args.schema or args.sample or args.summary)
            if args.tables:
                with client._cursor() as cur:
                    cur.execute("""
                        SELECT table_name FROM information_schema.tables
                        WHERE table_schema='public' AND table_type='BASE TABLE'
                        ORDER BY table_name
                    """)
                    rows = [r[0] for r in cur.fetchall()]
                    print("Public tables:")
                    for t in rows:
                        print(f" - {t}")
            if args.schema:
                table = args.schema
                if '.' in table:
                    schema, name = table.split('.', 1)
                else:
                    schema, name = 'public', table
                with client._cursor() as cur:
                    cur.execute("""
                        SELECT column_name, data_type
                        FROM information_schema.columns
                        WHERE table_schema=%s AND table_name=%s
                        ORDER BY ordinal_position
                    """, (schema, name))
                    print(f"Schema for {schema}.{name}:")
                    for col, typ in cur.fetchall():
                        print(f" - {col}: {typ}")
            if args.summary or want_default:
                stats = client.get_stats() or {}
                print("=== Summary ===")
                print(f"Active feeds: {stats.get('active_feeds', 0)}")
                print(f"Total articles: {stats.get('total_articles', 0)}")
                print(f"Articles (last 24h): {stats.get('articles_24h', 0)}")
                if stats.get('articles'):
                    print("Articles by status:")
                    for k, v in stats['articles'].items():
                        print(f"  {k}: {v}")
                # Extra counts
                with client._cursor() as cur:
                    cur.execute("SELECT COUNT(*) FROM articles_index WHERE COALESCE(ready_for_chunking,false)=true")
                    ready = cur.fetchone()[0]
                    cur.execute("SELECT COUNT(*) FROM articles_index WHERE COALESCE(chunking_completed,false)=true")
                    done = cur.fetchone()[0]
                    cur.execute("SELECT COUNT(*) FROM article_chunks")
                    chunks = cur.fetchone()[0]
                    print(f"Ready for chunking: {ready}")
                    print(f"Chunking completed: {done}")
                    print(f"Chunks total: {chunks}")
            if args.sample or want_default:
                n = args.sample or 5
                with client._cursor() as cur:
                    print("\n=== Samples ===")
                    cur.execute("SELECT id, feed_url, status, lang FROM feeds ORDER BY id DESC LIMIT %s", (n,))
                    print("feeds:")
                    for r in cur.fetchall():
                        print(f"  {r}")
                    cur.execute("""
                        SELECT id, source, LEFT(COALESCE(title,''), 80) AS title, status, published_at
                        FROM raw ORDER BY id DESC LIMIT %s
                    """, (n,))
                    print("raw:")
                    for r in cur.fetchall():
                        print(f"  {r}")
                    cur.execute("""
                        SELECT id, article_id, LEFT(COALESCE(title_norm,''), 80) AS title_norm,
                               COALESCE(ready_for_chunking,false) AS ready, COALESCE(chunking_completed,false) AS done
                        FROM articles_index ORDER BY id DESC LIMIT %s
                    """, (n,))
                    print("articles_index:")
                    for r in cur.fetchall():
                        print(f"  {r}")
                    cur.execute("""
                        SELECT id, article_id, chunk_index, LENGTH(COALESCE(text,'')) AS len, semantic_type
                        FROM article_chunks ORDER BY id DESC LIMIT %s
                    """, (n,))
                    print("article_chunks:")
                    for r in cur.fetchall():
                        print(f"  {r}")
            return

        # (removed duplicate index block; merged above)

        if args.cmd == "rag":
            logger.info("Starting Stage 8 RAG query")
            # Lazy import for RAG components
            from stage8_retrieval.rag_pipeline import RAGPipeline

            pipeline = RAGPipeline(client)
            
            try:
                response = pipeline.answer_query(
                    query=args.query,
                    limit=args.limit,
                    alpha=args.alpha
                )
                
                print(f"🔍 Processing query: '{args.query}'")
                print(f"   Search parameters: limit={args.limit}, alpha={args.alpha}\n")
                print(f"📰 Answer:\n{response.answer}\n")
                st = response.retrieval_info.get('search_type') if isinstance(getattr(response, 'retrieval_info', {}), dict) else None
                print("📊 Details:")
                print(f"   Sources used: {len(response.chunks_used)}")
                if st:
                    print(f"   Search type: {st}")
                print(f"   Total time: {response.total_time_ms:.1f}ms")

            except Exception as e:
                logger.error(f"RAG pipeline failed: {e}", exc_info=True)
            return

        if args.cmd == "report":
            logger.info("Generating system report")
            try:
                # Use new comprehensive system stats reporter
                from system_stats_reporter import SystemStatsReporter
                import asyncio

                reporter = SystemStatsReporter()

                # Generate comprehensive report
                stats = asyncio.run(reporter.collect_full_report())

                # Show console report
                console_report = reporter.format_report_for_bot(stats)
                print("=== System Report ===")
                print(console_report)

                # Send to Telegram if requested
                if args.send_telegram:
                    try:
                        success = asyncio.run(reporter.send_to_telegram(console_report))
                        if success:
                            print("✅ Report sent to Telegram successfully!")
                        else:
                            print("⚠️ Failed to send to Telegram (check credentials)")
                    except Exception as e:
                        logger.error(f"Failed to send Telegram report: {e}")
                        print(f"❌ Telegram send failed: {e}")

                # Save detailed stats
                import json
                with open('system_stats.json', 'w', encoding='utf-8') as f:
                    json.dump(stats, f, indent=2, ensure_ascii=False)
                print("💾 Detailed stats saved to system_stats.json")

            except Exception as e:
                logger.error(f"Report generation failed: {e}")
                print(f"❌ Report failed: {e}")

                # Fallback to old system
                try:
                    from report_generator import generate_report, send_telegram_report
                    report = generate_report(client, period_hours=args.period_hours, format=args.format)
                    print("=== Fallback Report ===")
                    print(report)
                    if args.send_telegram:
                        send_telegram_report(report, format=args.format)
                        print("✓ Fallback report sent to Telegram")
                except Exception as e2:
                    logger.error(f"Fallback report also failed: {e2}")
                    print(f"❌ All reporting systems failed: {e2}")
            return

        if args.cmd == "services":
            logger.info("Managing processing services")
            try:
                from services.service_manager import ServiceManager

                # Initialize service manager
                manager = ServiceManager(client)

                # Update intervals if provided
                if args.chunking_interval:
                    manager.service_configs['chunking']['interval'] = args.chunking_interval
                if args.fts_interval:
                    manager.service_configs['fts']['interval'] = args.fts_interval
                if args.embedding_interval:
                    manager.service_configs['embedding']['interval'] = args.embedding_interval

                # Validate and apply batch sizes
                if getattr(args, 'chunking_batch', None) is not None:
                    if args.chunking_batch < 10 or args.chunking_batch > 100:
                        raise ValueError("--chunking-batch must be between 10 and 100")
                    manager.chunking_batch_size = args.chunking_batch
                if getattr(args, 'embedding_batch', None) is not None:
                    if args.embedding_batch < 20 or args.embedding_batch > 5000:
                        raise ValueError("--embedding-batch must be between 20 and 5000")
                    manager.embedding_batch_size = args.embedding_batch
                if getattr(args, 'fts_batch', None) is not None:
                    if args.fts_batch < 100 or args.fts_batch > 200000:
                        raise ValueError("--fts-batch must be between 100 and 200000")
                    manager.fts_batch_size = args.fts_batch

                if args.action == "start":
                    # Start all services continuously
                    print("Starting RSS News services...")
                    try:
                        import asyncio
                        asyncio.run(manager.start_all_services())
                    except KeyboardInterrupt:
                        logger.info("Services stopped by user")
                    finally:
                        manager.stop_all_services()

                elif args.action == "run-once":
                    # Run services once
                    import asyncio
                    results = asyncio.run(manager.run_single_pass(args.services))
                    print("Service execution results:")
                    for service_name, result in results.items():
                        print(f"  {service_name}: {result}")

                elif args.action == "status":
                    # Get service status
                    import asyncio
                    status = asyncio.run(manager.get_service_status())
                    print("Service status:")
                    print(f"  Manager running: {status['service_manager_running']}")
                    for service_name, service_status in status['services'].items():
                        print(f"  {service_name}:")
                        for key, value in service_status.items():
                            print(f"    {key}: {value}")

            except Exception as e:
                logger.error(f"Services command failed: {e}")
                print(f"✗ Services error: {e}")
            return

        # Handle LlamaIndex commands (removed)
        if args.cmd.startswith("llamaindex-"):
            print("❌ LlamaIndex commands are not supported.")
            return 1

    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        print("\nInterrupted")
    except Exception as e:
        logger.error(f"Command failed: {e}")
        print(f"✗ Error: {e}")
        return 1
    finally:
        if client:
            client.close()
            
    return 0


if __name__ == "__main__":
    exit(main())
