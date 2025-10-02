# RSS News Aggregation System

A modern RSS news aggregation and processing system using local LLM models for intelligent article chunking and semantic search.

**Phase 3 Status:** ✅ 100% Complete (Agentic RAG, GraphRAG, Event Linking, Long-term Memory, A/B Testing)

## Architecture

**Local LLM Processing Pipeline:**
1. **RSS Polling** → Collect articles from RSS feeds
2. **Article Processing** → Extract and clean content
3. **Smart Chunking** → Qwen2.5-coder:3b creates semantic chunks
4. **Embeddings** → embeddinggemma generates 768-dim vectors
5. **Storage** → PostgreSQL with FTS and vector search

## Features

### Core System
- ✅ **RSS Feed Management** - Auto-discovery and polling
- ✅ **Smart Chunking** - AI-powered semantic segmentation
- ✅ **Local LLM Models** - No external API dependencies
- ✅ **Full-Text Search** - PostgreSQL FTS with automatic indexing
- ✅ **Vector Search** - Semantic similarity search via embeddings
- ✅ **Railway Deployment** - Cloud-ready with CloudFlare tunnel
- ✅ **Duplicate Detection** - Content-based deduplication

### Phase 3: Advanced AI (NEW)
- ✅ **Agentic RAG** - Iterative retrieval with self-checking
- ✅ **GraphRAG** - Knowledge graphs with advanced NER (spaCy/LLM)
- ✅ **Event Linking** - Temporal clustering with causality reasoning
- ✅ **Long-term Memory** - PostgreSQL + pgvector for semantic memory
- ✅ **A/B Testing** - Experiment framework with metrics tracking
- ✅ **Multi-Model Routing** - GPT-5, Claude 4.5, Gemini 2.5 Pro with fallbacks

## Local Models

**Qwen2.5-coder:3b** (via Ollama)
- Smart article chunking with semantic analysis
- Topic identification and structure recognition
- ~1.9GB, optimized for text processing

**embeddinggemma** (via Ollama)
- High-quality embeddings (768 dimensions)
- Semantic similarity and vector search
- ~593MB, specialized for embeddings

## Quick Start

1. **Set up environment:**
```bash
cp .env.example .env
# Edit .env with your database connection
```

2. **Install Ollama and models:**
```bash
# Install required models
ollama pull qwen2.5-coder:3b
ollama pull embeddinggemma
```

3. **Run the system:**
```bash
# Poll RSS feeds
python main.py poll

# Process articles (chunking + embeddings)
python main.py work

# Search articles
python main.py rag "AI technology news"
```

## Environment Variables

```bash
# Database (required)
PG_DSN=postgresql://user:pass@host:port/database

# Local LLM (required)
ENABLE_LOCAL_CHUNKING=true
ENABLE_LOCAL_EMBEDDINGS=true
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5-coder:3b
EMBEDDING_MODEL=embeddinggemma
```

## Commands

```bash
# RSS Management
python main.py poll              # Poll RSS feeds
python main.py discovery --feed <url>  # Add new feed

# Article Processing
python main.py work              # Process pending articles

# Search & Retrieval
python main.py rag "query"       # Semantic search
python main.py db-inspect        # Database statistics
python main.py report            # Generate reports

# Database
python main.py ensure            # Create/verify schema
```

## Railway Deployment

The system is designed for Railway deployment with local LLM models accessed via CloudFlare tunnel:

1. **Railway Services:**
   - RSS POLL (scheduled RSS collection)
   - RSS WORK (article processing)
   - PostgreSQL database

2. **Local Setup:**
   - Ollama with models
   - CloudFlare tunnel for external access

3. **Deploy:**
```bash
railway up
# Configure environment variables in Railway dashboard
```

## File Structure

```
rssnews/
├── main.py                    # Main CLI entry point
├── worker.py                  # Article processing worker
├── local_llm_chunker.py       # Qwen2.5-coder chunking
├── local_embedding_generator.py # embeddinggemma embeddings
├── pg_client_new.py           # PostgreSQL client
├── rss/                       # RSS polling and feed management
├── parser/                    # Content extraction
├── net/                       # HTTP client
└── utils/                     # Utilities
```

## Performance

**Typical Processing:**
- **RSS Polling:** ~112/118 feeds successful per cycle
- **Chunking:** 5-8 semantic chunks per article
- **Embeddings:** 768-dimensional vectors
- **Search:** Sub-second semantic queries

**Resource Usage:**
- **RAM:** ~4GB for both models
- **Storage:** Article chunks + embeddings in PostgreSQL
- **Network:** CloudFlare tunnel for Railway access

## Technology Stack

- **Python 3.11+** - Core runtime
- **PostgreSQL** - Data storage with FTS and vectors
- **Ollama** - Local LLM model serving
- **Railway** - Cloud deployment platform
- **CloudFlare** - Tunnel for external model access

---

Built with local-first AI processing for privacy and cost efficiency.