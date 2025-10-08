#!/usr/bin/env python3
"""
Simple Search Service - Bypasses complex RankingAPI
Direct semantic search using PgClient and OpenAI embeddings
"""

import logging
import os
from typing import List, Dict, Any
from dataclasses import dataclass

from pg_client_new import PgClient
from openai_embedding_generator import OpenAIEmbeddingGenerator

logger = logging.getLogger(__name__)


@dataclass
class SimpleSearchResult:
    """Simplified search result"""
    title: str
    text: str
    url: str
    source: str
    published_at: str
    similarity: float
    article_id: int
    chunk_id: int


class SimpleSearchService:
    """Simple search service using direct pgvector search"""

    def __init__(self):
        self.db = PgClient()
        self.embedding_gen = OpenAIEmbeddingGenerator()
        logger.info("✅ SimpleSearchService initialized")

    async def search(self, query: str, limit: int = 10) -> List[SimpleSearchResult]:
        """
        Perform semantic search

        Args:
            query: Search query
            limit: Maximum number of results

        Returns:
            List of search results
        """
        try:
            # Generate query embedding
            logger.info(f"Generating embedding for query: '{query}'")
            embeddings = await self.embedding_gen.generate_embeddings([query])

            if not embeddings or not embeddings[0]:
                logger.error("Failed to generate query embedding")
                return []

            query_embedding = embeddings[0]
            logger.info(f"✅ Generated {len(query_embedding)}-dim embedding")

            # Search using pgvector
            # Configurable minimum similarity threshold to avoid very weak matches
            try:
                min_sim = float(os.getenv('SIMPLE_SEARCH_MIN_SIM', '0.2'))
            except Exception:
                min_sim = 0.2

            logger.info(f"Searching with similarity threshold={min_sim}, limit={limit}")
            results = self.db.search_chunks_by_similarity(
                query_embedding=query_embedding,
                limit=limit,
                similarity_threshold=min_sim
            )

            logger.info(f"Found {len(results)} results")

            # Convert to SimpleSearchResult
            search_results = []
            for r in results:
                search_results.append(SimpleSearchResult(
                    title=r.get('title_norm', 'No title'),
                    text=r.get('text', '')[:500],  # First 500 chars
                    url=r.get('url', ''),
                    source=r.get('source_domain', 'unknown'),
                    published_at=str(r.get('published_at', '')),
                    similarity=r.get('similarity', 0.0),
                    article_id=r.get('article_id', 0),
                    chunk_id=r.get('id', 0)
                ))

            return search_results

        except Exception as e:
            logger.error(f"Search failed: {e}")
            import traceback
            traceback.print_exc()
            return []

    def format_results_for_telegram(self, results: List[SimpleSearchResult],
                                   query: str, max_results: int = 5) -> str:
        """
        Format search results for Telegram message

        Args:
            results: Search results
            query: Original query
            max_results: Maximum results to show

        Returns:
            Formatted markdown string
        """
        if not results:
            return f"🔍 No results found for: *{self._escape_md(query)}*"
        # Deduplicate by article_id to increase diversity
        unique: List[SimpleSearchResult] = []
        seen_ids = set()
        for r in results:
            aid = getattr(r, 'article_id', None)
            if aid is None or aid not in seen_ids:
                unique.append(r)
                if aid is not None:
                    seen_ids.add(aid)

        message = f"🔍 *Search Results for:* {self._escape_md(query)}\n"
        message += f"📊 Found {len(unique)} relevant articles\n\n"
        for i, result in enumerate(unique[:max_results], 1):
            similarity_percent = int(result.similarity * 100)

            title = self._escape_md(result.title)
            source = self._escape_md(result.source)
            url = result.url or ""
            message += f"*{i}. {title}*\n"
            message += f"📰 Source: {source}\n"
            message += f"🔗 {url}\n"
            message += f"📈 Relevance: {similarity_percent}%\n"
            message += f"📅 {result.published_at[:10]}\n"

            # Add snippet
            snippet = self._escape_md(result.text[:200])
            if len(result.text) > 200:
                snippet += "..."
            message += f"_{snippet}_\n\n"

        return message

    # --- helpers ---
    @staticmethod
    def _escape_md(text: str) -> str:
        if not text:
            return ""
        # Telegram MarkdownV2 escaping
        for ch in ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']:
            text = text.replace(ch, f"\\{ch}")
        return text
