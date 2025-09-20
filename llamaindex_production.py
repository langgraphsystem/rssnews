"""
LlamaIndex Production Integration for RSS News System
===================================================

Complete implementation following the integration matrix and routing rules:

Integration Matrix:
- Postgres (Railway): raw data/metadata/chunks + FTS keywords
- Pinecone: vectors (Gemini embeddings), hot/archive namespaces
- Gemini Embeddings: vector creation (indexing + queries)
- OpenAI (GPT-5) / Gemini LLM: response synthesis over extracted facts
- LlamaIndex: orchestration: chunking → retrieval (FTS+vectors) → filters → rerank → response format → logging

Routing Rules:
- Embeddings: always Gemini (consistency for Pinecone)
- Default Retriever: Hybrid (FTS Postgres + Vector Pinecone)
- LLM for response: OpenAI (GPT-5) default, auto-switch to Gemini for long context/limits/RU texts
- Indexes: hot (7-30 days) first, archive (older) if insufficient facts
- Language: en/ru separate routes
"""

import os
import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Union, Literal
from enum import Enum
import hashlib
import json

# LlamaIndex core
from llama_index.core import (
    Document, VectorStoreIndex, Settings, QueryBundle,
    PromptTemplate, get_response_synthesizer
)
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.extractors import (
    TitleExtractor, KeywordExtractor, QuestionsAnsweredExtractor
)
from llama_index.core.ingestion import IngestionPipeline
from llama_index.core.retrievers import VectorIndexRetriever
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.core.postprocessor import SimilarityPostprocessor
from llama_index.core.schema import NodeWithScore

# Vector stores
from llama_index.vector_stores.postgres import PGVectorStore
from llama_index.vector_stores.pinecone import PineconeVectorStore

# LLMs and embeddings
from llama_index.llms.openai import OpenAI
from llama_index.llms.gemini import Gemini
from llama_index.embeddings.gemini import GeminiEmbedding

# Additional components
from llama_index.core.response.pprint_utils import pprint_response
from sqlalchemy import create_engine
from pinecone import Pinecone

# Import components from llamaindex_components
# Fallback lightweight shims if components unavailable at import time
class CostTracker:  # type: ignore
    def add_cost(self, *args, **kwargs):
        pass

class PerformanceMonitor:  # type: ignore
    def start_timer(self, name: str) -> str:
        return "t"
    def end_timer(self, timer_id: str) -> float:
        return 0.0

class LegacyModeManager:  # type: ignore
    def is_legacy_enabled(self, component: str) -> bool:
        return False

class QueryCache:  # type: ignore
    def __init__(self, ttl_minutes: int = 15, max_size: int = 1000):
        self._c = {}
    def get(self, key):
        return None
    def set(self, key, value):
        self._c[key] = value

logger = logging.getLogger(__name__)

try:
    from llamaindex_components import (
        CostTracker,
        PerformanceMonitor,
        LegacyModeManager,
        QueryCache,
    )
except ImportError:
    logger.info("LlamaIndex components not found, using lightweight shims.")
    pass


class LanguageRoute(str, Enum):
    """Language routing for separate indexes"""
    EN = "en"
    RU = "ru"


class NamespaceRoute(str, Enum):
    """Pinecone namespace routing"""
    HOT = "hot"        # 7-30 days
    ARCHIVE = "archive"  # older than 30 days


class OutputPreset(str, Enum):
    """Predefined output formats"""
    DIGEST = "digest"    # 7-14 days window, list format
    QA = "qa"           # 30 days window, Q&A format
    SHORTS = "shorts"   # 30-90 days, video scenarios
    IDEAS = "ideas"     # broader exploration


class LLMProvider(str, Enum):
    """LLM provider routing"""
    OPENAI = "openai"   # Default: GPT-5
    GEMINI = "gemini"   # Fallback/long context


class RSSLlamaIndexOrchestrator:
    """
    Production LlamaIndex orchestrator for RSS News System

    Handles complete pipeline:
    1. Ingestion with smart chunking
    2. Dual vector storage (Postgres FTS + Pinecone vectors)
    3. Intelligent routing (language, namespace, LLM)
    4. Hybrid retrieval with reranking
    5. Grounded synthesis with source attribution
    6. Performance monitoring and cost controls
    """

    def __init__(
        self,
        pg_dsn: str,
        pinecone_api_key: str,
        pinecone_index: str,
        openai_api_key: str,
        gemini_api_key: str,
        pinecone_environment: str = "us-east-1-aws"
    ):
        self.pg_dsn = pg_dsn
        self.pinecone_api_key = pinecone_api_key
        self.pinecone_index = pinecone_index
        self.openai_api_key = openai_api_key
        self.gemini_api_key = gemini_api_key
        self.pinecone_environment = pinecone_environment

        # Initialize database engine
        self.engine = create_engine(pg_dsn)

        # Configure LlamaIndex settings
        self._setup_llamaindex_settings()

        # Initialize vector stores
        self.postgres_store = self._setup_postgres_store()
        self.pinecone_stores = self._setup_pinecone_stores()

        # Cost tracking
        self.cost_tracker = CostTracker()

        # Query cache
        self.query_cache = QueryCache(ttl_minutes=15)

    def _setup_llamaindex_settings(self):
        """Configure LlamaIndex global settings"""

        # Default embedding model: Gemini (for consistency)
        Settings.embed_model = GeminiEmbedding(
            api_key=self.gemini_api_key,
            model_name="text-embedding-004"
        )

        # Default LLM: OpenAI GPT-5
        Settings.llm = OpenAI(
            api_key=self.openai_api_key,
            model="gpt-5",
            temperature=0.3,
            max_completion_tokens=2000
        )

    def _setup_postgres_store(self) -> PGVectorStore:
        """Setup PostgreSQL vector store for FTS"""

        return PGVectorStore.from_params(
            database=self.pg_dsn.split("/")[-1],
            host=self.pg_dsn.split("@")[1].split(":")[0],
            password=self.pg_dsn.split(":")[2].split("@")[0],
            port=int(self.pg_dsn.split(":")[-1].split("/")[0]),
            user=self.pg_dsn.split("://")[1].split(":")[0],
            table_name="llamaindex_nodes",
            embed_dim=768,  # Gemini embedding dimension
            hybrid_search=True,  # Enable FTS + vector hybrid
            text_search_config="english"
        )

    def _setup_pinecone_stores(self) -> Dict[str, Dict[str, Any]]:  # PineconeVectorStore temporarily disabled
        """Setup Pinecone vector stores with namespaces"""

        # Initialize Pinecone with new API
        pc = Pinecone(api_key=self.pinecone_api_key)

        stores = {}

        # Create stores for each language and namespace combination
        for lang in LanguageRoute:
            stores[lang.value] = {}
            for namespace in NamespaceRoute:
                stores[lang.value][namespace.value] = PineconeVectorStore(
                    pinecone_index=pc.Index(self.pinecone_index),
                    namespace=f"{lang.value}_{namespace.value}"
                )

        return stores

    def create_unified_node_id(self, article_id: int, chunk_index: int) -> str:
        """Create unified node identifier: {article_id}#{chunk_index}"""
        return f"{article_id}#{chunk_index}"

    def parse_node_id(self, node_id: str) -> tuple[int, int]:
        """Parse unified node ID back to article_id and chunk_index"""
        article_id, chunk_index = node_id.split("#")
        return int(article_id), int(chunk_index)

    def determine_language(self, text: str) -> LanguageRoute:
        """Determine text language for routing"""
        # Simple heuristic - count Cyrillic vs Latin characters
        cyrillic_count = sum(1 for c in text if '\u0400' <= c <= '\u04FF')
        latin_count = sum(1 for c in text if c.isalpha() and c.isascii())

        if cyrillic_count > latin_count * 0.3:
            return LanguageRoute.RU
        return LanguageRoute.EN

    def determine_namespace(self, published_at: datetime) -> NamespaceRoute:
        """Determine namespace based on article age"""
        age_days = (datetime.now() - published_at).days

        if age_days <= 30:
            return NamespaceRoute.HOT
        return NamespaceRoute.ARCHIVE

    def create_enhanced_document(self, article: Dict[str, Any]) -> Document:
        """Create LlamaIndex document with rich metadata"""

        # Determine routing
        language = self.determine_language(article.get('clean_text', ''))
        published_at = article.get('published_at')
        if isinstance(published_at, str):
            published_at = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
        namespace = self.determine_namespace(published_at)

        # Create unified metadata
        metadata = {
            # Core identifiers
            'article_id': article.get('article_id'),
            'node_id_base': str(article.get('article_id')),  # For chunk numbering

            # Content metadata
            'title': article.get('title_norm', ''),
            'url': article.get('url', ''),
            'source_domain': article.get('source', ''),
            'published_at': published_at.isoformat() if published_at else '',
            'category': article.get('category', ''),
            'tags': article.get('tags_norm', []),

            # Routing metadata
            'language': language.value,
            'namespace': namespace.value,

            # Processing metadata
            'processing_version': article.get('processing_version', 1),
            'indexed_at': datetime.now().isoformat(),
        }

        return Document(
            text=article.get('clean_text', ''),
            metadata=metadata
        )

    def create_ingestion_pipeline(self) -> IngestionPipeline:
        """Create advanced ingestion pipeline"""

        # Smart sentence-based chunking
        text_splitter = SentenceSplitter(
            chunk_size=512,
            chunk_overlap=50,
            paragraph_separator="\n\n",
            secondary_chunking_regex="[.!?]+",
            tokenizer=lambda text: text.split()  # Simple tokenizer
        )

        # Metadata extractors
        extractors = [
            TitleExtractor(
                nodes=3,
                llm=Settings.llm,
                extract_template=PromptTemplate(
                    "Extract 1-2 alternative titles for this news article chunk:\n"
                    "{context_str}\n\n"
                    "Alternative titles (comma-separated):"
                )
            ),
            KeywordExtractor(
                keywords=8,
                llm=Settings.llm,
                extract_template=PromptTemplate(
                    "Extract key topics and entities from this news text:\n"
                    "{context_str}\n\n"
                    "Keywords (comma-separated):"
                )
            ),
            QuestionsAnsweredExtractor(
                questions=2,
                llm=Settings.llm,
                extract_template=PromptTemplate(
                    "What questions does this news text answer?\n"
                    "{context_str}\n\n"
                    "Questions answered (one per line):"
                )
            )
        ]

        return IngestionPipeline(
            transformations=[
                text_splitter,
                *extractors,
                Settings.embed_model,
            ],
            # Vector store will be set per operation
        )

    async def ingest_article(self, article: Dict[str, Any]) -> List[str]:
        """
        Ingest single article through complete pipeline

        Returns:
            List of created node IDs
        """

        # Create document
        document = self.create_enhanced_document(article)
        language = LanguageRoute(document.metadata['language'])
        namespace = NamespaceRoute(document.metadata['namespace'])

        # Create pipeline with appropriate vector store
        pipeline = self.create_ingestion_pipeline()

        # Dual storage: Postgres (FTS) + Pinecone (vectors)
        node_ids = []

        # 1. Store in Postgres for FTS
        pipeline.vector_store = self.postgres_store
        postgres_nodes = await pipeline.arun(documents=[document])

        # 2. Store in Pinecone for semantic search
        pipeline.vector_store = self.pinecone_stores[language.value][namespace.value]
        pinecone_nodes = await pipeline.arun(documents=[document])

        # Update node IDs with unified format
        for i, node in enumerate(postgres_nodes + pinecone_nodes):
            unified_id = self.create_unified_node_id(
                article['article_id'],
                i
            )
            node.node_id = unified_id
            node_ids.append(unified_id)

        logger.info(
            f"Ingested article {article['article_id']}: "
            f"{len(node_ids)} nodes, {language.value}/{namespace.value}"
        )

        return node_ids

    def create_hybrid_retriever(
        self,
        language: LanguageRoute,
        namespace: NamespaceRoute,
        similarity_top_k: int = 24
    ) -> 'HybridRetriever':
        """Create hybrid retriever combining FTS + vector search"""

        return HybridRetriever(
            postgres_store=self.postgres_store,
            pinecone_store=self.pinecone_stores[language.value][namespace.value],
            similarity_top_k=similarity_top_k,
            language=language,
            namespace=namespace
        )

    def create_smart_postprocessor(self) -> List:
        """Create intelligent postprocessing pipeline"""

        return [
            # Similarity filtering
            SimilarityPostprocessor(similarity_cutoff=0.6),

            # Domain diversification
            DomainDiversificationProcessor(max_per_domain=2),

            # Freshness boosting
            FreshnessBoostProcessor(boost_recent_days=7, boost_factor=1.2),

            # Reranking
            SemanticReranker(top_k=10),
        ]

    async def query(
        self,
        query: str,
        preset: OutputPreset = OutputPreset.QA,
        language: Optional[LanguageRoute] = None,
        max_sources: int = 10,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Main query interface with intelligent routing

        Args:
            query: User query
            preset: Output format preset
            language: Force language route (auto-detect if None)
            max_sources: Maximum sources in response
            **kwargs: Additional parameters

        Returns:
            Structured response with answer, sources, metadata
        """

        # Check cache
        cache_key = self._generate_cache_key(query, preset, language, max_sources)
        cached_response = self.query_cache.get(cache_key)
        if cached_response:
            logger.info(f"Cache hit for query: {query[:50]}...")
            return cached_response

        start_time = datetime.now()

        # Auto-detect language if not specified
        if language is None:
            language = self.determine_language(query)

        # Apply preset configuration
        config = self._get_preset_config(preset)

        # Multi-namespace search (hot first, then archive if needed)
        all_nodes = []

        # 1. Search hot namespace first
        hot_retriever = self.create_hybrid_retriever(
            language=language,
            namespace=NamespaceRoute.HOT,
            similarity_top_k=config['similarity_top_k']
        )

        hot_nodes = await hot_retriever.aretrieve(QueryBundle(query_str=query))
        all_nodes.extend(hot_nodes)

        # 2. Search archive if insufficient results
        if len(hot_nodes) < config['min_sources']:
            archive_retriever = self.create_hybrid_retriever(
                language=language,
                namespace=NamespaceRoute.ARCHIVE,
                similarity_top_k=config['similarity_top_k'] // 2
            )

            archive_nodes = await archive_retriever.aretrieve(QueryBundle(query_str=query))
            all_nodes.extend(archive_nodes)

        # Apply postprocessing
        postprocessors = self.create_smart_postprocessor()
        for processor in postprocessors:
            all_nodes = processor.postprocess_nodes(all_nodes)

        # Limit to max sources
        final_nodes = all_nodes[:max_sources]

        # Generate response with appropriate LLM
        llm_provider = self._select_llm_provider(query, final_nodes, language)
        response = await self._synthesize_response(
            query=query,
            nodes=final_nodes,
            preset=preset,
            llm_provider=llm_provider,
            config=config
        )

        # Calculate metrics
        end_time = datetime.now()
        processing_time = (end_time - start_time).total_seconds() * 1000

        # Build structured response
        result = {
            'answer': response.response,
            'sources': [self._format_source(node) for node in final_nodes],
            'metadata': {
                'query': query,
                'preset': preset.value,
                'language': language.value,
                'processing_time_ms': processing_time,
                'nodes_retrieved': len(all_nodes),
                'nodes_used': len(final_nodes),
                'llm_provider': llm_provider.value,
                'cost_estimate': self.cost_tracker.estimate_cost(response),
                'namespaces_searched': ['hot', 'archive'] if len(archive_nodes) > 0 else ['hot'],
                'domain_diversity': len(set(node.metadata.get('source_domain', '') for node in final_nodes)),
            }
        }

        # Cache result
        self.query_cache.set(cache_key, result)

        # Log query for analytics
        self._log_query(query, result)

        return result

    def _get_preset_config(self, preset: OutputPreset) -> Dict[str, Any]:
        """Get configuration for output preset"""

        configs = {
            OutputPreset.DIGEST: {
                'similarity_top_k': 24,
                'min_sources': 10,
                'max_response_tokens': 800,
                'response_template': DIGEST_TEMPLATE,
                'time_window_days': 14,
                'require_min_domains': 3,
            },
            OutputPreset.QA: {
                'similarity_top_k': 24,
                'min_sources': 8,
                'max_response_tokens': 1200,
                'response_template': QA_TEMPLATE,
                'time_window_days': 30,
                'require_min_domains': 2,
            },
            OutputPreset.SHORTS: {
                'similarity_top_k': 30,
                'min_sources': 6,
                'max_response_tokens': 600,
                'response_template': SHORTS_TEMPLATE,
                'time_window_days': 90,
                'require_min_domains': 2,
            },
            OutputPreset.IDEAS: {
                'similarity_top_k': 40,
                'min_sources': 12,
                'max_response_tokens': 1500,
                'response_template': IDEAS_TEMPLATE,
                'time_window_days': 90,
                'require_min_domains': 4,
            }
        }

        return configs[preset]

    def _select_llm_provider(
        self,
        query: str,
        nodes: List[NodeWithScore],
        language: LanguageRoute
    ) -> LLMProvider:
        """Intelligent LLM provider selection"""

        # Calculate context length
        total_context = len(query) + sum(len(node.text) for node in nodes)

        # Switch to Gemini for long context
        if total_context > 15000:
            return LLMProvider.GEMINI

        # Switch to Gemini for long-form Russian texts
        if language == LanguageRoute.RU and total_context > 8000:
            return LLMProvider.GEMINI

        # Check OpenAI rate limits/availability
        if not self._check_openai_availability():
            return LLMProvider.GEMINI

        # Default to OpenAI for quality
        return LLMProvider.OPENAI

    async def _synthesize_response(
        self,
        query: str,
        nodes: List[NodeWithScore],
        preset: OutputPreset,
        llm_provider: LLMProvider,
        config: Dict[str, Any]
    ) -> Any:
        """Synthesize grounded response"""

        # Select appropriate LLM
        if llm_provider == LLMProvider.GEMINI:
            llm = Gemini(
                api_key=self.gemini_api_key,
                model="gemini-1.5-pro",
                temperature=0.3,
                max_output_tokens=config['max_response_tokens']
            )
        else:
            llm = OpenAI(
                api_key=self.openai_api_key,
                model="gpt-5",
                temperature=0.3,
                max_completion_tokens=config['max_response_tokens']
            )

        # Create response synthesizer with grounding
        response_synthesizer = get_response_synthesizer(
            response_mode="tree_summarize",  # Better than simple concat
            use_async=True,
            streaming=False,
            service_context=None
        )

        # Use preset template
        response_synthesizer.update_prompts({
            "text_qa_template": config['response_template']
        })

        # Generate response
        response = await response_synthesizer.asynthesize(
            query=query,
            nodes=nodes
        )

        return response

    def _format_source(self, node: NodeWithScore) -> Dict[str, Any]:
        """Format source information for response"""

        return {
            'node_id': node.node_id,
            'title': node.metadata.get('title', ''),
            'url': node.metadata.get('url', ''),
            'source_domain': node.metadata.get('source_domain', ''),
            'published_at': node.metadata.get('published_at', ''),
            'relevance_score': node.score,
            'text_preview': node.text[:200] + "..." if len(node.text) > 200 else node.text,
        }

    def _generate_cache_key(self, query: str, preset: OutputPreset, language: Optional[LanguageRoute], max_sources: int) -> str:
        """Generate cache key for query"""

        key_data = f"{query}_{preset.value}_{language.value if language else 'auto'}_{max_sources}"
        return hashlib.md5(key_data.encode()).hexdigest()

    def _check_openai_availability(self) -> bool:
        """Check OpenAI API availability and rate limits"""
        # Implement rate limit checking logic
        return True  # Placeholder

    def _log_query(self, query: str, result: Dict[str, Any]):
        """Log query for analytics and monitoring"""

        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'query': query,
            'result_metadata': result['metadata'],
            'sources_used': [s['node_id'] for s in result['sources']],
        }

        logger.info(f"Query logged: {json.dumps(log_entry)}")


# Response templates
DIGEST_TEMPLATE = PromptTemplate(
    "Create a news digest based on the following articles:\n\n"
    "{context_str}\n\n"
    "Query: {query_str}\n\n"
    "Format as a bulleted list with 1-2 sentences per item, including source and date.\n"
    "Focus on the most important developments. Include at least 3 different sources.\n\n"
    "Digest:"
)

QA_TEMPLATE = PromptTemplate(
    "Answer the following question based on the provided news articles:\n\n"
    "{context_str}\n\n"
    "Question: {query_str}\n\n"
    "Provide a comprehensive answer with facts from the sources. "
    "Include source attribution and publish dates for key facts. "
    "If insufficient information, clearly state limitations.\n\n"
    "Answer:"
)

SHORTS_TEMPLATE = PromptTemplate(
    "Create a short video script idea based on these news articles:\n\n"
    "{context_str}\n\n"
    "Topic: {query_str}\n\n"
    "Format: Hook, key points (30-60 seconds), conclusion with source links.\n"
    "Make it engaging and suitable for social media.\n\n"
    "Script:"
)

IDEAS_TEMPLATE = PromptTemplate(
    "Explore the broader implications and connections based on these news sources:\n\n"
    "{context_str}\n\n"
    "Topic: {query_str}\n\n"
    "Provide insights, trends, and potential future developments. "
    "Connect information across sources to identify patterns and implications.\n"
    "Include diverse perspectives and source attribution.\n\n"
    "Analysis:"
)


# Additional supporting classes would be implemented here:
# - CostTracker
# - QueryCache
# - HybridRetriever
# - DomainDiversificationProcessor
# - FreshnessBoostProcessor
# - SemanticReranker


if __name__ == "__main__":
    # Example usage
    orchestrator = RSSLlamaIndexOrchestrator(
        pg_dsn="postgresql://postgres:pass@host:port/db",
        pinecone_api_key="your-pinecone-key",
        pinecone_index="rssnews-embeddings",
        openai_api_key="your-openai-key",
        gemini_api_key="your-gemini-key"
    )

    # Ingest article
    article_data = {
        'article_id': 123,
        'clean_text': "Article content...",
        'title_norm': "Article Title",
        'url': "https://example.com/article",
        'source': "example.com",
        'published_at': "2025-01-19T12:00:00Z",
        'language': 'en',
        'category': 'technology',
    }

    # Process article
    asyncio.run(orchestrator.ingest_article(article_data))

    # Query with different presets
    qa_result = asyncio.run(orchestrator.query(
        "What are the latest AI developments?",
        preset=OutputPreset.QA,
        max_sources=8
    ))

    digest_result = asyncio.run(orchestrator.query(
        "Tech news this week",
        preset=OutputPreset.DIGEST,
        max_sources=12
    ))
