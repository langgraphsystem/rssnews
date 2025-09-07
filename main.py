"""
Main CLI for RSS news aggregation system
"""

import argparse
import logging
import os
from datetime import datetime

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

    # Stage 6 chunking command
    p_chunk = sub.add_parser("chunk", help="Stage 6: deterministic chunking (LLM refine optional)")
    p_chunk.add_argument("--limit", type=int, default=20, help="Limit of articles to chunk")
    p_chunk.add_argument("--batch-size", type=int, default=20, help="Batch size for processing")

    # Stage 7 indexing command
    p_index = sub.add_parser("index", help="Stage 7: update FTS and embeddings")
    p_index.add_argument("--limit", type=int, default=128, help="Limit of chunks to index")

    # Stage 8 RAG command
    p_rag = sub.add_parser("rag", help="Stage 8: answer questions using RAG")
    p_rag.add_argument("query", help="Question to answer")
    p_rag.add_argument("--limit", type=int, default=10, help="Number of chunks to retrieve")
    p_rag.add_argument("--alpha", type=float, default=0.5, help="Weight for hybrid search (0=embedding, 1=FTS)")


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
            worker = ArticleWorker(
                client,
                batch_size=args.batch_size,
                max_workers=args.workers
            )
            
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

        if args.cmd == "chunk":
            logger.info("Starting Stage 6 chunking")
            # Lazy import to avoid overhead
            from chunking_simple import chunk_article
            from stage6_hybrid_chunking.src.stage6 import interfaces as st6_if

            total_articles = 0
            total_chunks = 0

            # Fetch ready articles
            articles = client.get_articles_ready_for_chunking(limit=args.limit)
            if not articles:
                print("No articles ready for chunking")
                return

            for art in articles:
                article_id = art.get('article_id')
                clean_text = art.get('clean_text') or ''
                processing_version = int(art.get('processing_version') or 1)

                # Build meta for denormalization
                meta = {
                    'url': art.get('url') or '',
                    'title_norm': art.get('title_norm') or '',
                    'source_domain': art.get('source') or '',
                    'published_at': art.get('published_at'),
                    'language': art.get('language') or '',
                    'category': art.get('category'),
                    'tags_norm': art.get('tags_norm') or [],
                }

                try:
                    # Deterministic pass
                    chunks = chunk_article(clean_text, meta)
                    # Optional LLM refine (annotations only, no boundary mutation here)
                    try:
                        refined = st6_if.refine_boundaries(chunks, {
                            'title_norm': meta['title_norm'],
                            'source_domain': meta['source_domain'],
                            'language': meta['language'],
                            'published_at': meta['published_at']
                        })
                        chunks = refined
                    except Exception as e:
                        logger.warning(f"LLM refine skipped: {e}")
                    # Decorate chunks with denorm fields
                    for c in chunks:
                        c.update({
                            'url': meta['url'],
                            'title_norm': meta['title_norm'],
                            'source_domain': meta['source_domain'],
                            'published_at': meta['published_at'],
                            'language': meta['language'],
                            'category': meta['category'],
                            'tags_norm': meta['tags_norm'],
                        })
                    client.upsert_article_chunks(article_id, processing_version, chunks)
                    client.mark_chunking_completed(article_id, processing_version)
                    total_articles += 1
                    total_chunks += len(chunks)
                except Exception as e:
                    logger.error(f"Failed chunking for {article_id}: {e}")

            print(f"✓ Chunking complete: articles={total_articles}, chunks={total_chunks}")
            return

        if args.cmd == "index":
            logger.info("Starting Stage 7 indexing")
            # Fetch chunks missing FTS/embeddings
            chunks = client.get_chunks_for_indexing(limit=args.limit)
            if not chunks:
                print("No chunks need indexing")
                return
            # Update FTS vectors first (safe, no external deps)
            try:
                ids = [c['id'] for c in chunks if 'id' in c]
                fts_updated = client.update_chunks_fts(ids)
                print(f"✓ Indexing complete: fts_updated={fts_updated}, considered={len(ids)}")
            except Exception as e:
                logger.error(f"Indexing failed: {e}")
                print(f"✗ Indexing failed: {e}")
            return

        if args.cmd == "rag":
            logger.info("Starting Stage 8 RAG retrieval")
            try:
                from stage8_retrieval.retriever import HybridRetriever
                retriever = HybridRetriever(client)
                res = retriever.hybrid_retrieve(args.query, limit=args.limit, alpha=args.alpha)
                print("=== RAG Results ===")
                print(f"Query (normalized): {res.query_normalized}")
                print(f"Search type: {res.search_type}")
                print(f"Results: {len(res.chunks)}")
                for i, ch in enumerate(res.chunks, 1):
                    title = ch.get('title_norm') or ch.get('title') or ''
                    url = ch.get('url') or ''
                    src = ch.get('source_domain') or ch.get('source') or ''
                    print(f"[{i}] {title} | {src} | {url}")
            except Exception as e:
                logger.error(f"RAG retrieval failed: {e}")
                print(f"✗ RAG retrieval failed: {e}")
            return

        if args.cmd == "index":
            logger.info("Starting Stage 7 indexing (FTS + embeddings)")
            from stage6_hybrid_chunking.src.config.settings import get_settings
            from stage6_hybrid_chunking.src.llm.gemini_client import GeminiClient
            settings = get_settings()

            chunks = client.get_chunks_for_indexing(limit=128)
            if not chunks:
                print("No chunks pending indexing")
                return
            ids = [row['id'] for row in chunks]
            updated_fts = client.update_chunks_fts(ids)
            emb_count = 0
            try:
                if settings.gemini.embedding_model:
                    texts = [row.get('text', '') for row in chunks]
                    # Budget guard: rough per-text token estimate -> cost
                    budget_cap = settings.rate_limit.embedding_daily_cost_limit_usd
                    est_cost = 0.0
                    selected = []
                    for t, row in zip(texts, chunks):
                        tokens = max(1, len(t) // 4)
                        cost = tokens * settings.rate_limit.cost_per_token_input
                        if est_cost + cost > budget_cap:
                            continue
                        est_cost += cost
                        selected.append((t, row))
                    if selected:
                        import asyncio
                        async def _do_embed(pairs):
                            gc = GeminiClient(settings)
                            try:
                                vecs = await gc.embed_texts([p[0] for p in pairs])
                            finally:
                                await gc.close()
                            return vecs
                        vectors = asyncio.get_event_loop().run_until_complete(_do_embed(selected))
                        for (t, row), vec in zip(selected, vectors):
                            if vec:
                                ok = client.update_chunk_embedding(row['id'], vec)
                                if ok:
                                    emb_count += 1
            except Exception as e:
                logger.warning(f"Embedding step failed/disabled: {e}")

            print(f"✓ Indexing complete: fts_updated={updated_fts}, embeddings_updated={emb_count}")
            return

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
