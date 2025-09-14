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
            try:
                import asyncio
                # embed_texts is async, so we need to await it
                embeddings = asyncio.run(gemini_client.embed_texts([query]))
            except RuntimeError:
                # Fallback if an event loop is already running
                loop = asyncio.get_event_loop()
                embeddings = loop.run_until_complete(gemini_client.embed_texts([query]))
            
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
        self.pinecone_client = None

        # Initialize Pinecone if available
        try:
            from stage6_hybrid_chunking.src.vector.pinecone_client import PineconeClient
            pc = PineconeClient()
            if pc.enabled and pc.connect():
                self.pinecone_client = pc
                logger.info("Pinecone client initialized for hybrid search")
        except Exception as e:
            logger.info(f"Pinecone not available for search: {e}")
        
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
                # Embedding only - prefer Pinecone if available
                query_vector = self.embedding_client.get_query_embedding(normalized_query)
                if query_vector and self.pinecone_client:
                    # Search in Pinecone then get full chunks from PostgreSQL
                    pinecone_results = self.pinecone_client.search(query_vector, top_k=limit)
                    chunk_ids = [int(r['id']) for r in pinecone_results if r.get('id')]
                    chunks = self.pg_client.get_chunks_by_ids(chunk_ids) if chunk_ids else []
                    # Add Pinecone scores to chunks
                    score_map = {int(r['id']): r['score'] for r in pinecone_results}
                    for chunk in chunks:
                        chunk['pinecone_score'] = score_map.get(chunk.get('id'), 0.0)
                    search_type = "pinecone_embedding"
                    logger.info(f"Performing Pinecone embedding search with alpha={alpha}")
                elif query_vector:
                    # Fallback to PostgreSQL embedding search
                    chunks = self.pg_client.search_chunks_embedding(query_vector, limit)
                    search_type = "postgres_embedding"
                    logger.info(f"Performing PostgreSQL embedding search with alpha={alpha}")
                else:
                    # Fallback to FTS if embedding fails
                    chunks = self.pg_client.search_chunks_fts(normalized_query, limit)
                    search_type = "fts_fallback"
                    logger.warning("Embedding failed, falling back to FTS")
                    
            else:
                # Hybrid search - combine FTS and Pinecone/PostgreSQL embedding
                query_vector = self.embedding_client.get_query_embedding(normalized_query)
                if query_vector:
                    # Get FTS results
                    fts_chunks = self.pg_client.search_chunks_fts(normalized_query, limit * 2)

                    # Get embedding results
                    if self.pinecone_client:
                        pinecone_results = self.pinecone_client.search(query_vector, top_k=limit * 2)
                        chunk_ids = [int(r['id']) for r in pinecone_results if r.get('id')]
                        emb_chunks = self.pg_client.get_chunks_by_ids(chunk_ids) if chunk_ids else []
                        # Add Pinecone scores
                        score_map = {int(r['id']): r['score'] for r in pinecone_results}
                        for chunk in emb_chunks:
                            chunk['pinecone_score'] = score_map.get(chunk.get('id'), 0.0)
                        search_type = "hybrid_pinecone"
                    else:
                        emb_chunks = self.pg_client.search_chunks_embedding(query_vector, limit * 2)
                        search_type = "hybrid_postgres"

                    # Combine and rerank results
                    chunks = self._combine_results(fts_chunks, emb_chunks, alpha, limit)
                    logger.info(f"Performing {search_type} search with alpha={alpha}")
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

    def _combine_results(self, fts_chunks: List[Dict], emb_chunks: List[Dict], alpha: float, limit: int) -> List[Dict]:
        """Combine FTS and embedding results using weighted scoring.

        Args:
            fts_chunks: Results from FTS search
            emb_chunks: Results from embedding search
            alpha: Weight for FTS vs embedding (0.0=embedding only, 1.0=FTS only)
            limit: Maximum number of results to return

        Returns:
            Combined and reranked results
        """
        # Create lookup maps by chunk ID
        fts_map = {}
        for i, chunk in enumerate(fts_chunks):
            chunk_id = chunk.get('id')
            if chunk_id:
                # FTS score: higher rank = lower score (inverse ranking)
                fts_score = 1.0 / (i + 1)
                chunk['fts_score'] = fts_score
                fts_map[chunk_id] = chunk

        emb_map = {}
        for i, chunk in enumerate(emb_chunks):
            chunk_id = chunk.get('id')
            if chunk_id:
                # Embedding score: use Pinecone score if available, otherwise ranking
                emb_score = chunk.get('pinecone_score', 1.0 / (i + 1))
                chunk['emb_score'] = emb_score
                emb_map[chunk_id] = chunk

        # Combine results with hybrid scoring
        combined = {}
        all_chunk_ids = set(fts_map.keys()) | set(emb_map.keys())

        for chunk_id in all_chunk_ids:
            fts_chunk = fts_map.get(chunk_id)
            emb_chunk = emb_map.get(chunk_id)

            # Use the chunk with more complete data
            chunk = fts_chunk or emb_chunk

            # Calculate hybrid score
            fts_score = fts_chunk['fts_score'] if fts_chunk else 0.0
            emb_score = emb_chunk['emb_score'] if emb_chunk else 0.0

            hybrid_score = alpha * fts_score + (1.0 - alpha) * emb_score
            chunk['hybrid_score'] = hybrid_score

            combined[chunk_id] = chunk

        # Sort by hybrid score and return top results
        sorted_chunks = sorted(combined.values(), key=lambda x: x['hybrid_score'], reverse=True)
        return sorted_chunks[:limit]

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
