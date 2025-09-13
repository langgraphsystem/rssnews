# Stage 6-7 Testing Runbook

## Overview

Stage 6-7 implements deterministic chunking with selective LLM refinement (Stage 6) and full-text search indexing with embeddings (Stage 7) for the RSS News Pipeline.

## Running Tests Locally

### Prerequisites

```bash
# Ensure you're in project root
cd /path/to/rssnews

# Activate virtual environment
source .venv/bin/activate  # Linux/Mac
# or
.\.venv\Scripts\Activate.ps1  # Windows PowerShell

# Install test dependencies (if not already installed)
pip install -r requirements.txt
```

### Environment Variables

Set these environment variables for testing:

```bash
# Required for database connection (can be fake for tests)
export PG_DSN="postgresql://user:pass@localhost:5432/test_db"

# Optional: LLM configuration (mocked in tests)
export GEMINI_API_KEY="test_key"
export EMBEDDING_MODEL="gemini-embedding-001"
export LLM_MAX_SHARE=0.3
export LLM_DAILY_COST_CAP_USD=100.0
export EMB_DAILY_COST_CAP_USD=100.0
```

For Windows PowerShell:
```powershell
$env:PG_DSN = "postgresql://user:pass@localhost:5432/test_db"
$env:GEMINI_API_KEY = "test_key"
```

### Running Individual Test Suites

```bash
# Run all Stage 6-7 tests
python -m pytest tests/test_chunk_index_e2e.py tests/test_budget_guards.py -v

# Run E2E test only
python -m pytest tests/test_chunk_index_e2e.py -v

# Run budget guard tests only  
python -m pytest tests/test_budget_guards.py -v

# Run all prerequisite tests (should all be green)
python -m pytest tests/test_quality_router.py tests/test_llm_client.py tests/test_post_validators.py tests/test_overlap.py -v

# Run all tests with quiet output
python -m pytest tests/ -q
```

### Skip E2E Tests (if needed)

If you need to skip E2E tests due to environment constraints:

```bash
# Skip E2E tests
python -m pytest tests/ -k "not e2e" -v

# Skip budget tests  
python -m pytest tests/ -k "not budget" -v
```

## Test Architecture

### Fixtures (`tests/fixtures/`)

- **`sample_article.py`**: Provides `sample_article_en()` with structured test content:
  - Long paragraph (triggers chunking)
  - Short paragraph 
  - Bullet list (3 items)
  - Quote line

- **`mock_llm.py`**: `MockGeminiClient` with deterministic behavior:
  - LLM refinement: merge short chunks, split long ones, retype notes
  - Embeddings: returns fixed 8-dimensional vectors
  - Cost tracking for budget tests

- **`mock_pg.py`**: `FakePgClient` providing in-memory database simulation:
  - Stage 6 API: articles ready for chunking, chunk upserts
  - Stage 7 API: chunk indexing, FTS updates, embedding storage

### Test Files

- **`test_chunk_index_e2e.py`**: End-to-end test running both stages:
  - Creates sample article, runs chunking, verifies chunks created
  - Runs indexing, verifies FTS vectors and embeddings added
  - Tests idempotency (re-running doesn't duplicate)

- **`test_budget_guards.py`**: Budget constraint testing:
  - LLM daily budget: stops refinement when cost cap exceeded
  - Embedding daily budget: stops embedding when cost cap exceeded

## Database Fixture

The tests use an in-memory mock database (`FakePgClient`) that simulates the PostgreSQL interface without requiring actual database setup. This ensures:

- No external dependencies in CI/CD
- Fast test execution (<5s for E2E)
- Deterministic results
- No network calls

If you need to test against real PostgreSQL:

1. Set up test database:
```sql
CREATE DATABASE rssnews_test;
```

2. Run schema setup:
```bash
python main.py ensure
```

3. Modify test to use real `PgClient` (not recommended for CI)

## Troubleshooting

### Common Issues

1. **Import errors**: Make sure you're running from project root with `python -m pytest`

2. **Missing attributes in settings**: Check that all required settings attributes are present in test stubs

3. **Async warnings**: These are expected due to asyncio usage in main code and can be ignored

4. **Pydantic deprecation warnings**: Expected, code works correctly

### Expected Test Results

All tests should pass:
- `test_chunk_index_e2e`: Creates chunks, applies FTS/embeddings
- `test_llm_daily_budget_guard`: First chunk refined, others skipped due to budget
- `test_embeddings_budget_guard`: Some chunks get embeddings, others skipped due to budget

### Performance

- E2E test: ~1-2 seconds
- Budget tests: ~0.5 seconds each
- Full test suite: ~5 seconds

## Stage Behavior

### Stage 6 (Chunking + LLM Refinement)
- Deterministic text chunking with word boundaries
- Quality router decides which chunks need LLM refinement
- MockGeminiClient applies deterministic edits (merge/split/retype)
- Budget guards prevent excessive LLM usage
- Post-validation ensures no overlaps/gaps

### Stage 7 (FTS + Embeddings)
- Full-text search vector creation (PostgreSQL tsvector)
- Embedding generation via MockGeminiClient (deterministic 8-dim vectors)
- Budget guards prevent excessive embedding costs
- Idempotent: re-running doesn't change results

## Integration Points

The tests verify integration between:
- CLI commands (`main.py chunk`, `main.py index`)
- Database operations (chunk storage, status updates)
- LLM client integration (mocked but realistic)
- Configuration system (environment variables, settings)
- Quality routing and post-validation logic