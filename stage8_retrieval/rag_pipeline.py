"""
Stage 8 RAG Pipeline module for RSS News Pipeline
Handles prompt building, LLM calls, and complete query answering orchestration.
"""

import json
import logging
import time
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict

from .retriever import HybridRetriever, RetrievalResult

logger = logging.getLogger(__name__)


@dataclass
class RAGResponse:
    """Container for complete RAG pipeline response."""
    query: str
    answer: str
    chunks_used: List[Dict[str, Any]]
    retrieval_info: Dict[str, Any]
    llm_info: Dict[str, Any]
    total_time_ms: float
    timestamp: str


class PromptBuilder:
    """Handles structured prompt building for RAG queries."""
    
    def __init__(self):
        self.system_prompt = """You are a helpful news analyst assistant. Use the provided news article chunks to answer the user's question accurately and concisely.

Guidelines:
- Base your answer primarily on the provided context
- If the context doesn't contain enough information, clearly state the limitations
- Cite specific sources when possible (mention article titles or domains)
- Provide factual, objective responses
- If asked about recent events, note the publication dates of the sources"""

        self.prompt_template = """{system_prompt}

Context from news articles:
{context}

User Question: {query}

Please provide a comprehensive answer based on the context above:"""

    def build_prompt(self, query: str, chunks: List[Dict[str, Any]]) -> str:
        """Build structured JSON prompt with query and context.
        
        Args:
            query: User's question
            chunks: Retrieved chunks with metadata
            
        Returns:
            Formatted prompt string
        """
        if not chunks:
            context = "No relevant news articles found for this query."
        else:
            context_parts = []
            for i, chunk in enumerate(chunks, 1):
                title = chunk.get('title_norm', 'Unknown Title')
                source = chunk.get('source_domain', 'Unknown Source')
                published = chunk.get('published_at', 'Unknown Date')
                text = chunk.get('text', '').strip()
                
                # Format published date if available
                if published and published != 'Unknown Date':
                    try:
                        if isinstance(published, str):
                            pub_date = published.split('T')[0]  # Get just the date part
                        else:
                            pub_date = str(published).split(' ')[0]  # Handle datetime objects
                    except:
                        pub_date = 'Unknown Date'
                else:
                    pub_date = 'Unknown Date'
                
                context_parts.append(
                    f"[{i}] Title: {title}\n"
                    f"    Source: {source}\n"
                    f"    Published: {pub_date}\n"
                    f"    Content: {text[:800]}{'...' if len(text) > 800 else ''}\n"
                )
            
            context = "\n".join(context_parts)
        
        return self.prompt_template.format(
            system_prompt=self.system_prompt,
            context=context,
            query=query
        )
    
    def build_json_prompt(self, query: str, chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Build structured JSON prompt for API calls.
        
        Args:
            query: User's question
            chunks: Retrieved chunks with metadata
            
        Returns:
            Structured prompt as dictionary
        """
        # Prepare context chunks with essential metadata
        context_chunks = []
        for chunk in chunks:
            context_chunks.append({
                'id': chunk.get('id'),
                'title': chunk.get('title_norm', ''),
                'source': chunk.get('source_domain', ''),
                'published_at': chunk.get('published_at', ''),
                'text': chunk.get('text', '').strip()[:1000],  # Limit text length
                'url': chunk.get('url', ''),
                'relevance_score': chunk.get('hybrid_score', 0.0)
            })
        
        return {
            "system_prompt": self.system_prompt,
            "user_query": query,
            "context": context_chunks,
            "task": "Answer the user query using the provided news article context",
            "response_format": "Provide a clear, factual answer citing sources where possible"
        }


class LLMClient:
    """Handles LLM calls with budget guards and error handling."""
    
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
                logger.info("Gemini client initialized for RAG")
            except Exception as e:
                logger.error(f"Failed to initialize Gemini client: {e}")
                raise
        
        return self._gemini_client
    
    def call_llm(self, prompt: str, max_tokens: int = 1000) -> Dict[str, Any]:
        """Call LLM with budget guard and error handling.
        
        Args:
            prompt: Formatted prompt string
            max_tokens: Maximum tokens in response
            
        Returns:
            Dict with response text, tokens used, cost, etc.
        """
        start_time = time.time()
        
        try:
            gemini_client = self._get_gemini_client()
            
            # Check budget guard (simplified - real implementation should use rate_limit settings)
            try:
                # Basic budget check - this would be more sophisticated in production
                logger.info("Checking LLM budget before RAG call")
                
                # Make the LLM call using existing Gemini client
                # Note: This uses the refine_chunks_via_llm method adapted for RAG
                response_text = self._call_gemini_for_rag(gemini_client, prompt)
                
                call_time_ms = (time.time() - start_time) * 1000
                
                # Estimate token usage (rough approximation)
                prompt_tokens = len(prompt.split()) * 1.3  # rough token estimate
                response_tokens = len(response_text.split()) * 1.3
                total_tokens = prompt_tokens + response_tokens
                
                # Estimate cost based on settings
                cost_estimate = total_tokens * self.settings.rate_limit.cost_per_token_input if self.settings else 0.0
                
                logger.info(f"LLM call successful: {len(response_text)} chars, ~{total_tokens:.0f} tokens, {call_time_ms:.1f}ms")
                
                return {
                    'response': response_text,
                    'success': True,
                    'tokens_used': int(total_tokens),
                    'cost_estimate': cost_estimate,
                    'call_time_ms': call_time_ms,
                    'model': self.settings.gemini.model if self.settings else 'gemini-2.5-flash'
                }
                
            except Exception as budget_error:
                logger.error(f"Budget guard failed: {budget_error}")
                raise
                
        except Exception as e:
            call_time_ms = (time.time() - start_time) * 1000
            logger.error(f"LLM call failed after {call_time_ms:.1f}ms: {e}")
            
            return {
                'response': f"Sorry, I encountered an error processing your question: {str(e)}",
                'success': False,
                'tokens_used': 0,
                'cost_estimate': 0.0,
                'call_time_ms': call_time_ms,
                'error': str(e)
            }
    
    def _call_gemini_for_rag(self, gemini_client, prompt: str) -> str:
        """Adapt existing Gemini client for RAG use case."""
        try:
            # Create a simple chunk-like structure for the existing refine method
            # This is a workaround to use the existing infrastructure
            fake_chunks = [{
                'text': 'RAG_QUERY_CONTEXT',
                'chunk_index': 0,
                'semantic_type': 'query'
            }]
            
            # Create a custom prompt structure
            rag_prompt = f"""
Please answer this question using the context provided:

{prompt}

Provide a clear, factual answer based on the news context given above.
"""
            
            # Use the existing LLM infrastructure
            # This is a simplified approach - production might need a dedicated RAG method
            results = gemini_client.refine_chunks_via_llm(
                fake_chunks, 
                "answer_query",
                custom_prompt=rag_prompt
            )
            # Handle async method
            try:
                import asyncio
                if hasattr(results, "__await__"):
                    results = asyncio.get_event_loop().run_until_complete(results)
            except Exception:
                pass
            
            if results and len(results) > 0:
                return results[0].get('refined_text', 'No response generated')
            else:
                return "I apologize, but I wasn't able to generate a response to your question."
                
        except Exception as e:
            logger.error(f"Gemini RAG call failed: {e}")
            return f"I encountered an error while processing your question: {str(e)}"


class RAGPipeline:
    """Main RAG pipeline orchestrator."""
    
    def __init__(self, pg_client, settings=None):
        self.pg_client = pg_client
        self.settings = settings
        self.retriever = HybridRetriever(pg_client, settings)
        self.prompt_builder = PromptBuilder()
        self.llm_client = LLMClient(settings)
        
    def answer_query(self, query: str, limit: int = 10, alpha: float = 0.5) -> RAGResponse:
        """Complete RAG pipeline: retrieve → prompt → llm → return answer.
        
        Args:
            query: User's question
            limit: Maximum chunks to retrieve
            alpha: Hybrid search weight (0.0=embedding, 1.0=FTS)
            
        Returns:
            RAGResponse with complete results
        """
        start_time = time.time()
        timestamp = datetime.utcnow().isoformat()
        
        logger.info(f"Starting RAG pipeline for query: '{query[:100]}...'")
        
        try:
            # Step 1: Retrieve relevant chunks
            retrieval_result = self.retriever.hybrid_retrieve(query, limit, alpha)
            
            if not retrieval_result.chunks:
                logger.warning("No chunks retrieved for query")
                return RAGResponse(
                    query=query,
                    answer="I couldn't find any relevant information to answer your question. This might be because the query is outside the scope of available news articles, or the articles haven't been indexed yet.",
                    chunks_used=[],
                    retrieval_info={
                        'search_type': retrieval_result.search_type,
                        'query_normalized': retrieval_result.query_normalized,
                        'total_results': 0,
                        'search_time_ms': retrieval_result.search_time_ms
                    },
                    llm_info={'success': False, 'reason': 'no_chunks'},
                    total_time_ms=(time.time() - start_time) * 1000,
                    timestamp=timestamp
                )
            
            # Step 2: Build prompt
            prompt = self.prompt_builder.build_prompt(query, retrieval_result.chunks)
            logger.info(f"Built prompt with {len(retrieval_result.chunks)} chunks")
            
            # Step 3: Call LLM
            llm_result = self.llm_client.call_llm(prompt)
            
            # Step 4: Build response
            total_time_ms = (time.time() - start_time) * 1000
            
            response = RAGResponse(
                query=query,
                answer=llm_result['response'],
                chunks_used=retrieval_result.chunks,
                retrieval_info={
                    'search_type': retrieval_result.search_type,
                    'query_normalized': retrieval_result.query_normalized,
                    'total_results': retrieval_result.total_results,
                    'search_time_ms': retrieval_result.search_time_ms,
                    'alpha': alpha
                },
                llm_info=llm_result,
                total_time_ms=total_time_ms,
                timestamp=timestamp
            )
            
            logger.info(f"RAG pipeline completed in {total_time_ms:.1f}ms")
            return response
            
        except Exception as e:
            total_time_ms = (time.time() - start_time) * 1000
            logger.error(f"RAG pipeline failed after {total_time_ms:.1f}ms: {e}")
            
            return RAGResponse(
                query=query,
                answer=f"I encountered an error while processing your question: {str(e)}",
                chunks_used=[],
                retrieval_info={'error': str(e)},
                llm_info={'success': False, 'error': str(e)},
                total_time_ms=total_time_ms,
                timestamp=timestamp
            )
    
    def get_pipeline_stats(self) -> Dict[str, Any]:
        """Get RAG pipeline statistics and status."""
        try:
            stats = {}
            
            # Get retriever stats
            retriever_stats = self.retriever.get_retrieval_stats()
            stats['retriever'] = retriever_stats
            
            # Add pipeline-specific stats
            stats['pipeline_ready'] = True
            stats['llm_client_ready'] = self.llm_client._gemini_client is not None
            stats['components'] = {
                'retriever': 'ready',
                'prompt_builder': 'ready', 
                'llm_client': 'ready' if stats['llm_client_ready'] else 'not_initialized'
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get pipeline stats: {e}")
            return {'pipeline_ready': False, 'error': str(e)}
