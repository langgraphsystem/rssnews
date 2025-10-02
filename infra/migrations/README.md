# Database Migrations

This directory contains SQL migration scripts for the RSSnews project.

## Prerequisites

### pgvector Extension

The memory system requires the `pgvector` extension for vector similarity search.

**Installation:**

```bash
# Ubuntu/Debian
sudo apt install postgresql-15-pgvector

# macOS (via Homebrew)
brew install pgvector

# Docker
# Use postgres image with pgvector pre-installed:
# docker pull pgvector/pgvector:pg15
```

**Railway.app:**
Railway PostgreSQL includes pgvector by default. No installation needed.

## Running Migrations

### Manual Execution

```bash
# Connect to database
psql $PG_DSN

# Run migration
\i infra/migrations/001_create_memory_records.sql
```

### Python Script (Recommended)

```bash
python scripts/run_migrations.py
```

## Migrations

### 001_create_memory_records.sql

**Purpose:** Create `memory_records` table for Phase 3 long-term memory.

**Features:**
- Vector embeddings (1536-dim for OpenAI text-embedding-3-small)
- Automatic expiration based on TTL
- Multi-tenant support (user_id)
- Tags and metadata
- Access tracking
- Vector similarity index (IVFFlat)

**Schema:**

```sql
CREATE TABLE memory_records (
    id UUID PRIMARY KEY,
    type VARCHAR(32),  -- 'episodic' or 'semantic'
    content TEXT,
    embedding vector(1536),
    importance FLOAT,
    ttl_days INTEGER,
    expires_at TIMESTAMP,
    refs TEXT[],
    user_id VARCHAR(128),
    tags TEXT[],
    created_at TIMESTAMP,
    accessed_at TIMESTAMP,
    access_count INTEGER,
    metadata JSONB
);
```

**Indexes:**
- `idx_memory_records_type` - Filter by type
- `idx_memory_records_user_id` - Multi-tenant queries
- `idx_memory_records_embedding` - Vector similarity (IVFFlat)
- `idx_memory_records_tags` - GIN index for tag searches

**Functions:**
- `update_memory_expires_at()` - Auto-compute expiration date
- `cleanup_expired_memories()` - Batch delete expired records
- `update_memory_access()` - Track access patterns

## Verification

After running migrations, verify the schema:

```sql
-- Check table exists
\dt memory_records

-- Check indexes
\di memory_records*

-- Check pgvector extension
SELECT * FROM pg_extension WHERE extname = 'vector';

-- Test vector operations
SELECT embedding <=> '[0.1, 0.2, ...]'::vector AS distance
FROM memory_records
LIMIT 1;
```

## Rollback

### 001_create_memory_records.sql

```sql
DROP TABLE IF EXISTS memory_records CASCADE;
DROP FUNCTION IF EXISTS update_memory_expires_at() CASCADE;
DROP FUNCTION IF EXISTS cleanup_expired_memories() CASCADE;
DROP FUNCTION IF EXISTS update_memory_access() CASCADE;
```

## Usage Examples

### Store a memory

```python
from core.memory.memory_store import create_memory_store

store = create_memory_store()
memory_id = await store.store(
    content="Important fact about AI trends...",
    memory_type="semantic",
    importance=0.8,
    ttl_days=90,
    refs=["article_123"],
    user_id="user_456",
    tags=["AI", "trends"]
)
```

### Semantic search

```python
results = await store.recall(
    query="AI adoption trends",
    user_id="user_456",
    top_k=5,
    min_similarity=0.7
)
```

### Cleanup expired memories

```sql
SELECT cleanup_expired_memories();
-- Returns: number of deleted records
```

## Performance Considerations

### Vector Index

The IVFFlat index provides approximate nearest neighbor search with O(sqrt(N)) complexity.

**Tuning:**
- `lists` parameter: 100 for <100K records, 1000 for >1M records
- Rebuild index after bulk inserts: `REINDEX INDEX idx_memory_records_embedding;`

### Query Optimization

```sql
-- Use cosine distance for normalized embeddings
SELECT *, embedding <=> query_vector AS distance
FROM memory_records
WHERE user_id = $1
ORDER BY distance
LIMIT 10;

-- Use L2 distance for non-normalized
SELECT *, embedding <-> query_vector AS distance
FROM memory_records
ORDER BY distance
LIMIT 10;
```

## Monitoring

### Table size

```sql
SELECT pg_size_pretty(pg_total_relation_size('memory_records'));
```

### Index usage

```sql
SELECT schemaname, tablename, indexname, idx_scan, idx_tup_read
FROM pg_stat_user_indexes
WHERE tablename = 'memory_records';
```

### Expired records

```sql
SELECT COUNT(*) FROM memory_records WHERE expires_at < NOW();
```
