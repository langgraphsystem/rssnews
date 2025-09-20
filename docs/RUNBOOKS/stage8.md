# Stage 8 Retrieval & RAG Runbook

## Overview

Stage 8 implements the final retrieval and question-answering layer of the RSS News Pipeline. It provides hybrid search capabilities combining full-text search (FTS) with semantic embeddings, and a complete Retrieval-Augmented Generation (RAG) pipeline for answering questions using news content.

## Architecture

### Components

1. **Query Normalization** (`QueryNormalizer`)
   - Preprocesses user queries with stop word removal
   - Handles special characters and whitespace
   - Optimizes queries for both FTS and embedding search

2. **Hybrid Search** (`HybridRetriever`)
   - Combines PostgreSQL FTS with pgvector embedding similarity
   - Alpha weighting: 0.0=embedding only, 1.0=FTS only, 0.5=balanced
   - Automatic fallback to FTS when embedding fails
   - Score normalization and ranking

3. **RAG Pipeline** (`RAGPipeline`)
   - Structured prompt building with context formatting
   - LLM integration with budget guards
   - Complete query orchestration and response formatting

### Search Methods

- **FTS Search**: Uses PostgreSQL `plainto_tsquery` with BM25 ranking
- **Embedding Search**: Uses pgvector cosine similarity on text-embedding-004 vectors  
- **Hybrid Search**: Weighted combination with normalized scores

## Usage

### CLI Interface

```bash
# Basic RAG query
python main.py rag "What are the latest AI developments?"

# Limit results
python main.py rag "Tesla earnings" --limit 5

# FTS-only search (fastest)
python main.py rag "breaking news" --alpha 1.0

# Embedding-only search (most semantic)
python main.py rag "climate change impacts" --alpha 0.0

# Balanced hybrid search (default)
python main.py rag "market trends" --alpha 0.5
```

### Output Format

```
🔍 Processing query: 'What are the latest AI developments?'
   Search parameters: limit=10, alpha=0.5

📰 Answer:
Based on recent news reports, AI development is advancing rapidly with several key breakthroughs...

📊 Details:
   Sources used: 3
   Search type: hybrid
   Query normalized: 'latest ai developments'
   Total time: 1247.3ms

📖 Sources:
   [1] OpenAI Model Updates (GPT-5 Turbo)
       Source: openai.com
       URL: https://openai.com
   [2] Google Quantum Computing Breakthrough
       Source: googleblog.com
       URL: https://googleblog.com/quantum
```

## Configuration

### Environment Variables

Required:
```bash
# Database connection
export PG_DSN="postgresql://user:pass@host:port/database"

# LLM API key (for embeddings and text generation)
export GEMINI_API_KEY="your_api_key_here"
```

Optional:
```bash
# Model configuration
export GEMINI_MODEL="gemini-2.5-flash"
export EMBEDDING_MODEL="text-embedding-004"

# Budget controls
export LLM_DAILY_COST_CAP_USD=50.0
export EMB_DAILY_COST_CAP_USD=10.0
export LLM_MAX_SHARE=0.3
```

### Alpha Parameter Guide

- **α = 0.0**: Pure semantic search - best for conceptual queries
- **α = 0.25**: Embedding-heavy - good for related concepts  
- **α = 0.5**: Balanced hybrid - recommended default
- **α = 0.75**: FTS-heavy - good for specific terms
- **α = 1.0**: Pure keyword search - fastest, exact matches

## Prerequisites

Before using Stage 8, ensure the previous stages are complete:

```bash
# 1. Database schema exists
python main.py ensure

# 2. Articles are processed and chunked (Stage 6)
python main.py chunk --limit 100

# 3. Chunks are indexed with FTS and embeddings (Stage 7)
python main.py index --limit 100

# 4. Verify data readiness
python main.py stats --detailed
```

Expected stats output:
```
Active feeds: 25
Total articles: 5000
Articles (last 24h): 150

Articles by status:
  ready_for_chunking: 0
  chunking_complete: 4500
  indexed: 4200
```

## Testing

### Running Tests

```bash
# Run all Stage 8 tests
python -m pytest tests/test_retriever.py tests/test_rag_pipeline.py tests/test_rag_e2e.py -v

# Component tests only
python -m pytest tests/test_retriever.py -v
python -m pytest tests/test_rag_pipeline.py -v

# End-to-end tests
python -m pytest tests/test_rag_e2e.py -v

# Skip slow E2E tests
python -m pytest tests/test_retriever.py tests/test_rag_pipeline.py -v
```

### Test Coverage

- **Retriever Tests**: Query normalization, embedding client, hybrid search, alpha weighting
- **RAG Pipeline Tests**: Prompt building, LLM client, response formatting, error handling
- **E2E Tests**: Complete workflows with mock DB and LLM, realistic scenarios

### Environment for Testing

```bash
# Minimal test environment
export PG_DSN="postgresql://test:test@localhost:5432/test_db"
export GEMINI_API_KEY="test_key"  # Mocked in tests

# Run tests (no real API calls)
python -m pytest tests/test_rag_*.py -v
```

## Performance

### Search Performance

- **FTS Search**: ~10-50ms for 10K chunks
- **Embedding Search**: ~20-100ms for 10K chunks  
- **Hybrid Search**: ~30-150ms for 10K chunks
- **Total RAG Time**: ~500-2000ms including LLM call

### Optimization Tips

1. **Use appropriate alpha values**:
   - Fast queries: α=1.0 (FTS only)
   - Semantic queries: α=0.0 (embedding only)

2. **Limit result counts**:
   - --limit 5 for quick answers
   - --limit 20 for comprehensive research

3. **Pre-filter by category/date** (future enhancement):
   - Add category filters to search methods
   - Time-based filtering for recent news

## Troubleshooting

### Common Issues

1. **"No chunks retrieved for query"**
   - Check if Stage 7 indexing is complete: `python main.py stats`
   - Verify chunks exist: check `chunks` table in database
   - Try different alpha values (0.0, 0.5, 1.0)

2. **"Embedding client failed"**
   - Check GEMINI_API_KEY is set correctly
   - Verify internet connectivity for API calls  
   - Check budget limits haven't been exceeded
   - Falls back to FTS search automatically

3. **"LLM call failed"**
   - Check API key and quotas
   - Verify prompt length isn't excessive
   - Budget guard may have triggered (check logs)

4. **Poor search quality**
   - Try different alpha values for your query type
   - Check if query normalization is too aggressive
   - Verify chunks contain relevant content

### Debug Commands

```bash
# Check database status
python main.py stats --detailed

# Test individual search methods (via psql)
SELECT COUNT(*) FROM chunks WHERE fts_vector IS NOT NULL;
SELECT COUNT(*) FROM chunks WHERE embedding IS NOT NULL;

# Check query normalization
python -c "
from stage8_retrieval.retriever import QueryNormalizer
qn = QueryNormalizer()
print(qn.normalize_query('Your query here'))
"

# Test embedding generation
python -c "
from stage8_retrieval.retriever import EmbeddingClient
ec = EmbeddingClient()  
print(ec.get_query_embedding('test query'))
"
```

### Error Codes

- **RetrievalResult.search_type == "error"**: Database or search failure
- **RetrievalResult.search_type == "fts_fallback"**: Embedding failed, using FTS
- **RAGResponse.llm_info.success == False**: LLM call failed
- **RAGResponse.chunks_used == []**: No relevant content found

## Query Examples

### Technology News
```bash
python main.py rag "AI breakthroughs 2024" --alpha 0.5
python main.py rag "OpenAI GPT quantum computing" --alpha 0.3
python main.py rag "tech IPO market analysis" --alpha 0.7
```

### Business & Finance  
```bash
python main.py rag "Tesla earnings Q4" --alpha 1.0
python main.py rag "cryptocurrency market trends" --alpha 0.4
python main.py rag "inflation impact economy" --alpha 0.6
```

### Science & Environment
```bash
python main.py rag "climate change latest research" --alpha 0.2
python main.py rag "space exploration missions" --alpha 0.5
python main.py rag "renewable energy developments" --alpha 0.4
```

### General News
```bash
python main.py rag "breaking news today" --alpha 1.0
python main.py rag "political developments" --alpha 0.6
python main.py rag "global health updates" --alpha 0.3
```

## Integration

### Database Schema Requirements

Stage 8 requires these database tables and columns:

```sql
-- Chunks table with FTS and embedding columns (from Stage 7)
ALTER TABLE chunks ADD COLUMN fts_vector tsvector;
ALTER TABLE chunks ADD COLUMN embedding vector(768);

-- Indexes for performance
CREATE INDEX chunks_fts_idx ON chunks USING gin(fts_vector);
CREATE INDEX chunks_embedding_idx ON chunks USING ivfflat (embedding vector_cosine_ops);
```

### API Integration (Future)

The RAG pipeline components are designed for easy integration:

```python
from stage8_retrieval.rag_pipeline import RAGPipeline
from pg_client_new import PgClient

# Initialize
client = PgClient()
pipeline = RAGPipeline(client)

# Query
response = pipeline.answer_query("your question", limit=10, alpha=0.5)

# Access structured results
print(response.answer)
print(f"Used {len(response.chunks_used)} sources")
print(f"Search took {response.total_time_ms:.1f}ms")
```

## Future Enhancements

1. **Category Filtering**: Add `--category technology` filter to CLI
2. **Date Filtering**: Add `--since 2024-01-01` for recent news only  
3. **Multi-language**: Support non-English queries and content
4. **Caching**: Cache embedding vectors for repeated queries
5. **Streaming**: Stream LLM responses for better UX
6. **Feedback Loop**: Learn from user feedback to improve ranking

## Security

- API keys are loaded from environment variables only
- No user input is passed directly to shell commands
- Database queries use parameterized statements
- LLM prompts are sanitized and structured
- Budget guards prevent runaway API costs
