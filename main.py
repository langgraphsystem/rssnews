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

    # Report command
    p_report = sub.add_parser("report", help="Generate and send system report")
    p_report.add_argument("--send-telegram", action="store_true", help="Send report to Telegram")
    p_report.add_argument("--period-hours", type=int, default=8, help="Report period in hours (default: 8)")
    p_report.add_argument("--format", choices=["markdown", "html"], default="html", help="Report format (default: html)")

    # LlamaIndex commands
    try:
        from llamaindex_cli import add_llamaindex_commands
        add_llamaindex_commands(sub)
    except ImportError:
        logger.warning("LlamaIndex CLI not available - install dependencies or check llamaindex_cli.py")

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

            # 2) Try embeddings if configured (PG vector or Pinecone)
            emb_count = 0
            try:
                from stage6_hybrid_chunking.src.config.settings import get_settings  # lazy import
                from stage6_hybrid_chunking.src.llm.gemini_client import GeminiClient
                # Optional Pinecone integration
                from stage6_hybrid_chunking.src.vector.pinecone_client import PineconeClient
                settings = get_settings()

                logger.info(f"Checking embedding settings: has_model={bool(settings.gemini.embedding_model)}")
                if settings.gemini.embedding_model:
                    logger.info(f"Embedding model configured: {settings.gemini.embedding_model}")
                    texts = [row.get('text', '') for row in chunks]
                    # Budget guard: rough token estimate -> cost cap
                    budget_cap = settings.rate_limit.embedding_daily_cost_limit_usd
                    logger.info(f"Budget cap: ${budget_cap}, cost per token: ${settings.rate_limit.cost_per_token_input}")
                    est_cost = 0.0
                    selected = []
                    for t, row in zip(texts, chunks):
                        tokens = max(1, len(t) // 4)
                        cost = tokens * settings.rate_limit.cost_per_token_input
                        if est_cost + cost > budget_cap:
                            logger.info(f"Budget exceeded at chunk {row['id']}: cost {est_cost + cost} > cap {budget_cap}")
                            continue
                        est_cost += cost
                        selected.append((t, row))
                    logger.info(f"Selected {len(selected)}/{len(chunks)} chunks for embedding (estimated cost: ${est_cost})")
                    if selected:
                        import asyncio
                        async def _do_embed(pairs):
                            gc = GeminiClient(settings)
                            try:
                                vecs = await gc.embed_texts([p[0] for p in pairs])
                            finally:
                                await gc.close()
                            return vecs
                        try:
                            vectors = asyncio.run(_do_embed(selected))
                        except RuntimeError:
                            # Fallback if an event loop is already running
                            loop = asyncio.get_event_loop()
                            vectors = loop.run_until_complete(_do_embed(selected))
                        # If Pinecone configured, upsert there; otherwise fall back to PG update
                        pnc = PineconeClient()
                        used_pinecone = False
                        logger.info(f"Pinecone enabled: {pnc.enabled}, vectors generated: {len(vectors)}")
                        if pnc.enabled and pnc.connect():
                            logger.info("Pinecone connection successful")
                            payload = []
                            for i, ((t, row), vec) in enumerate(zip(selected, vectors)):
                                logger.info(f"Vector {i}: type={type(vec)}, len={len(vec) if hasattr(vec, '__len__') else 'N/A'}, sample={vec[:3] if vec and hasattr(vec, '__len__') and len(vec) > 0 else vec}")
                                if vec and isinstance(vec, list) and len(vec) > 0:
                                    payload.append({
                                        'id': str(row['id']),
                                        'values': vec,
                                        'metadata': {
                                            'article_id': str(row.get('article_id') or ''),
                                            'chunk_index': int(row.get('chunk_index') or 0),
                                            'language': row.get('language') or ''
                                        }
                                    })
                                else:
                                    logger.warning(f"Skipping invalid vector {i} for chunk {row['id']}: {vec}")
                            logger.info(f"Prepared {len(payload)} vectors for Pinecone upsert")
                            if payload:
                                emb_count = pnc.upsert(payload)
                                used_pinecone = emb_count > 0
                                logger.info(f"Pinecone upsert result: {emb_count} vectors")
                        else:
                            logger.info("Pinecone connection failed or not enabled")
                        if not used_pinecone:
                            # Fallback: store in Postgres column if available
                            for (t, row), vec in zip(selected, vectors):
                                if vec:
                                    ok = client.update_chunk_embedding(row['id'], vec)
                                    if ok:
                                        emb_count += 1
            except Exception as e:
                logger.warning(f"Embedding step skipped/failed: {e}")

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

                # Optional: generate LLM answer over top context
                if args.answer and collapsed:
                    try:
                        import asyncio
                        # Prefer OpenAI Responses API if OPENAI_API_KEY is present
                        # Build context up to max chars
                        ctx = []
                        total = 0
                        for idx, ch in enumerate(collapsed, 1):
                            piece = f"[{idx}] {ch.get('title_norm') or ''}\n{(ch.get('text') or '')}\nSource: {ch.get('source_domain') or ''} | {ch.get('url') or ''}\n\n"
                            if total + len(piece) > args.max_context:
                                break
                            ctx.append(piece)
                            total += len(piece)
                        context_text = '\n'.join(ctx)
                        lang = args.answer_lang.lower()
                        # Split на system + user
                        if lang.startswith('ru'):
                            system_prompt = "Отвечай кратко на русском. Используй только факты из контекста. Добавляй сноски [n] к фактам."
                            user_prompt = f"Вопрос: {args.query}\n\nКонтекст:\n{context_text}\n\nОтвет:"
                        else:
                            system_prompt = "Answer concisely in English. Use only facts from the context. Add [n] citations to facts."
                            user_prompt = f"Question: {args.query}\n\nContext:\n{context_text}\n\nAnswer:"

                        async def _gen_openai(sys_p: str, usr_p: str) -> str:
                            try:
                                from llm_helper import generate_response_text  # type: ignore
                            except Exception:
                                return "(LLM helper not available)"
                            try:
                                return await generate_response_text(
                                    usr_p,
                                    instructions=sys_p,
                                    model="gpt-5",
                                    store=True,
                                    max_output_tokens=4000,
                                    retries=3,
                                )
                            except Exception as e:
                                return f"(LLM call failed: {e})"

                        try:
                            answer = asyncio.run(_gen_openai(system_prompt, user_prompt))
                        except RuntimeError:
                            loop = asyncio.get_event_loop()
                            answer = loop.run_until_complete(_gen_openai(system_prompt, user_prompt))
                        print("\n=== LLM Answer ===")
                        print(answer.strip() or "(пустой ответ)")
                        print("\nSources:")
                        for i, ch in enumerate(collapsed, 1):
                            print(f"[{i}] {ch.get('title_norm') or ''} | {ch.get('source_domain') or ''} | {ch.get('url') or ''}")
                    except Exception as e:
                        logger.warning(f"LLM answer skipped: {e}")
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
                from report_generator import generate_report, send_telegram_report, send_enhanced_telegram_report

                # Generate basic report for console
                report = generate_report(
                    client,
                    period_hours=args.period_hours,
                    format=args.format
                )

                print("=== System Report ===")
                print(report)

                # Send to Telegram if requested
                if args.send_telegram:
                    try:
                        # Use enhanced report with GPT analysis for Telegram
                        import asyncio
                        try:
                            asyncio.run(send_enhanced_telegram_report(client, args.period_hours))
                        except RuntimeError:
                            # Fallback if event loop is already running
                            loop = asyncio.get_event_loop()
                            loop.run_until_complete(send_enhanced_telegram_report(client, args.period_hours))
                        print("✓ Enhanced report with GPT analysis sent to Telegram")
                    except Exception as e:
                        logger.error(f"Failed to send enhanced Telegram report: {e}")
                        # Fallback to basic report
                        try:
                            send_telegram_report(report, format=args.format)
                            print("✓ Basic report sent to Telegram (GPT analysis failed)")
                        except Exception as e2:
                            logger.error(f"Failed to send basic Telegram report: {e2}")
                            print(f"✗ Telegram send failed: {e}")

            except Exception as e:
                logger.error(f"Report generation failed: {e}")
                print(f"✗ Report failed: {e}")
            return

        # Handle LlamaIndex commands
        if args.cmd.startswith("llamaindex-"):
            try:
                from llamaindex_cli import handle_llamaindex_commands
                import asyncio

                # Run async LlamaIndex commands
                try:
                    result = asyncio.run(handle_llamaindex_commands(args))
                except RuntimeError:
                    # Fallback if event loop is already running
                    loop = asyncio.get_event_loop()
                    result = loop.run_until_complete(handle_llamaindex_commands(args))

                return result

            except ImportError:
                logger.error("LlamaIndex CLI not available")
                print("❌ LlamaIndex not installed. Install with: pip install llama-index")
                return 1
            except Exception as e:
                logger.error(f"LlamaIndex command failed: {e}")
                print(f"❌ LlamaIndex error: {e}")
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
