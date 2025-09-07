"""
Stage 8 Retrieval module for RSS News Pipeline
Handles query normalization, embedding generation, and hybrid search orchestration.
"""

import re
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class RetrievalResult:
    """Container for retrieval results with metadata."""
    chunks: List[Dict[str, Any]]
    query_normalized: str
    search_type: str  # "fts", "embedding", "hybrid"
    total_results: int
    search_time_ms: float


class QueryNormalizer:
    """Handles query preprocessing and normalization."""
    
    def __init__(self):
        # Common stop words for better FTS results
        self.stop_words = {
            'a', 'an', 'and', 'are', 'as', 'at', 'be', 'by', 'for', 'from',
            'has', 'he', 'in', 'is', 'it', 'its', 'of', 'on', 'that', 'the',
            'to', 'was', 'will', 'with', 'the', 'this', 'but', 'they', 'have',
            'had', 'what', 'said', 'each', 'which', 'she', 'do', 'how', 'their',
            'if', 'up', 'out', 'many', 'then', 'them', 'these', 'so', 'some',
        }
        
    def normalize_query(self, query: str) -> str:
        """Normalize query for better search results.
        
        Args:
            query: Raw user query
            
        Returns:
            Normalized query string
        """
        if not query or not query.strip():
            return ""
        
        # Basic normalization
        normalized = query.strip().lower()
        
        # Remove extra whitespace
        normalized = re.sub(r'\s+', ' ', normalized)
        
        # Remove special characters that might interfere with FTS
        normalized = re.sub(r'[^\w\s\-\']', ' ', normalized)
        
        # Split into words and filter
        words = normalized.split()
        
        # Remove stop words and very short words
        filtered_words = []
        for word in words:
            if len(word) >= 2 and word not in self.stop_words:
                filtered_words.append(word)
        
        # If all words were filtered out, return original (normalized)
        if not filtered_words:
            return re.sub(r'[^\w\s\-\']', ' ', query.strip().lower())
        
        return ' '.join(filtered_words)


class EmbeddingClient:
    """Handles embedding generation via Gemini API."""
    
    def __init__(self, settings=None):
        self.settings = settings
        self._gemini_client = None
        
    def _get_gemini_client(self):
        """Lazy initialization of Gemini client."""
        if self._gemini_client is None:
            try:
                from stage6_hybrid_chunking.src.llm.gemini_client import GeminiClient
                from stage6_hybrid_chunking.src.config.settings import get_settings
                
                if self.settings is None:
                    self.settings = get_settings()
                
                self._gemini_client = GeminiClient(self.settings)
                logger.info("Gemini client initialized for embeddings")
            except Exception as e:
                logger.error(f"Failed to initialize Gemini client: {e}")
                raise
        
        return self._gemini_client
    
    def get_query_embedding(self, query: str) -> Optional[List[float]]:
        """Generate embedding vector for query using Gemini API.
        
        Args:
            query: Query text to embed
            
        Returns:
            Embedding vector or None if failed
        """
        if not query or not query.strip():
            return None
        
        try:
            gemini_client = self._get_gemini_client()
            
            # Use embed_texts method from existing GeminiClient
            embeddings = gemini_client.embed_texts([query])
            # Handle async client method
            try:
                import asyncio
                if hasattr(embeddings, "__await__"):
                    embeddings = asyncio.get_event_loop().run_until_complete(embeddings)
            except Exception:
                pass
            
            if embeddings and len(embeddings) > 0:
                return embeddings[0]
            else:
                logger.warning(f"No embedding generated for query: {query[:50]}")
                return None
                
        except Exception as e:
            logger.error(f"Failed to generate embedding for query: {e}")
            return None


class HybridRetriever:
    """Main retriever class that orchestrates hybrid search."""
    
    def __init__(self, pg_client, settings=None):
        self.pg_client = pg_client
        self.query_normalizer = QueryNormalizer()
        self.embedding_client = EmbeddingClient(settings)
        
    def hybrid_retrieve(self, query: str, limit: int = 10, alpha: float = 0.5) -> RetrievalResult:
        """Perform hybrid retrieval combining FTS and embedding search.
        
        Args:
            query: User query string
            limit: Maximum number of results to return
            alpha: Weight for FTS vs embedding (0.0=embedding only, 1.0=FTS only)
            
        Returns:
            RetrievalResult with chunks and metadata
        """
        import time
        start_time = time.time()
        
        # Normalize query
        normalized_query = self.query_normalizer.normalize_query(query)
        logger.info(f"Query normalized: '{query}' -> '{normalized_query}'")
        
        if not normalized_query:
            logger.warning("Empty query after normalization")
            return RetrievalResult(
                chunks=[],
                query_normalized="",
                search_type="none",
                total_results=0,
                search_time_ms=0.0
            )
        
        try:
            # Determine search strategy
            if alpha >= 1.0:
                # FTS only
                chunks = self.pg_client.search_chunks_fts(normalized_query, limit)
                search_type = "fts"
                logger.info(f"Performing FTS-only search with alpha={alpha}")
                
            elif alpha <= 0.0:
                # Embedding only
                query_vector = self.embedding_client.get_query_embedding(normalized_query)
                if query_vector:
                    chunks = self.pg_client.search_chunks_embedding(query_vector, limit)
                    search_type = "embedding"
                    logger.info(f"Performing embedding-only search with alpha={alpha}")
                else:
                    # Fallback to FTS if embedding fails
                    chunks = self.pg_client.search_chunks_fts(normalized_query, limit)
                    search_type = "fts_fallback"
                    logger.warning("Embedding failed, falling back to FTS")
                    
            else:
                # Hybrid search
                query_vector = self.embedding_client.get_query_embedding(normalized_query)
                if query_vector:
                    chunks = self.pg_client.hybrid_search(normalized_query, query_vector, limit, alpha)
                    search_type = "hybrid"
                    logger.info(f"Performing hybrid search with alpha={alpha}")
                else:
                    # Fallback to FTS if embedding fails
                    chunks = self.pg_client.search_chunks_fts(normalized_query, limit)
                    search_type = "fts_fallback"
                    logger.warning("Embedding failed in hybrid mode, falling back to FTS")
            
            search_time_ms = (time.time() - start_time) * 1000
            
            logger.info(f"Retrieved {len(chunks)} chunks in {search_time_ms:.1f}ms using {search_type}")
            
            return RetrievalResult(
                chunks=chunks,
                query_normalized=normalized_query,
                search_type=search_type,
                total_results=len(chunks),
                search_time_ms=search_time_ms
            )
            
        except Exception as e:
            search_time_ms = (time.time() - start_time) * 1000
            logger.error(f"Retrieval failed after {search_time_ms:.1f}ms: {e}")
            
            return RetrievalResult(
                chunks=[],
                query_normalized=normalized_query,
                search_type="error",
                total_results=0,
                search_time_ms=search_time_ms
            )
    
    def get_retrieval_stats(self) -> Dict[str, Any]:
        """Get retrieval system statistics."""
        try:
            # Get some basic stats from the database
            stats = self.pg_client.get_stats()
            
            # Add retrieval-specific stats
            stats['retrieval_ready'] = True
            stats['embedding_client_ready'] = self.embedding_client._gemini_client is not None
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get retrieval stats: {e}")
            return {'retrieval_ready': False, 'error': str(e)}
