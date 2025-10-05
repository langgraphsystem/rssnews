# Railway Multi-Service Configuration

## Overview

Project uses `launcher.py` with `railway.toml` for multi-service deployment. Each service runs different commands based on `SERVICE_MODE` environment variable.

**Architecture:** All continuous services (WORK, CHUNK, OpenAIEmbending) automatically process new items as they appear, creating a fully automated pipeline.

## Services Configuration

### 1. RSS POLL Service (Cron)
**Service ID:** `d116f94c-c0f7-4712-82a8-283258d05de4`

**Environment Variables:**
```bash
SERVICE_MODE=poll
POLL_WORKERS=10
POLL_BATCH=10
```

**Command:** `python main.py poll --workers 10 --batch-size 10`

**Purpose:** Polls RSS feeds and ingests new articles into `raw` table

**Mode:** Cron (scheduled via Railway)

---

### 2. WORK Service (Continuous)
**Service ID:** `4692233a-27bd-4e1c-b4e2-142f7cc59601`

**Environment Variables:**
```bash
SERVICE_MODE=work-continuous
WORK_CONTINUOUS_INTERVAL=30
WORK_CONTINUOUS_BATCH=50
WORK_WORKERS=10
```

**Command:** `python services/work_continuous_service.py --interval 30 --batch 50`

**Purpose:** Continuously processes pending articles from `raw` table (fulltext extraction, NLP, metadata enrichment)

**Mode:** Continuous (checks every 30s for new articles with status='pending')

**Monitoring:**
```bash
railway run python -c "from services.work_continuous_service import WorkContinuousService; s = WorkContinuousService(); print(s.get_backlog_stats())"
```

---

### 3. CHUNK Service (Continuous)
**Service ID:** `f32c1205-d7e4-429b-85ea-e8b00d897334`

**Environment Variables:**
```bash
SERVICE_MODE=chunk-continuous
CHUNK_CONTINUOUS_INTERVAL=30
CHUNK_CONTINUOUS_BATCH=100
```

**Command:** `python services/chunk_continuous_service.py --interval 30 --batch 100`

**Purpose:** Continuously processes articles that need chunking using Qwen2.5-coder via Ollama

**Mode:** Continuous (checks every 30s for articles without chunks)

**Monitoring:**
```bash
railway run python -c "from services.chunk_continuous_service import ChunkContinuousService; s = ChunkContinuousService(); print(s.get_backlog_stats())"
```

---

### 4. OpenAIEmbending Service (Continuous)
**Service ID:** `c015bdb5-710d-46b8-ad86-c566b99e7560`

**Environment Variables:**
```bash
SERVICE_MODE=openai-migration
MIGRATION_INTERVAL=60
OPENAI_API_KEY=sk-proj-...
OPENAI_EMBEDDING_MODEL=text-embedding-3-large
OPENAI_EMBEDDING_BATCH_SIZE=100
OPENAI_EMBEDDING_MAX_RETRIES=3
```

**Command:** `python services/openai_embedding_migration_service.py --interval 60`

**Purpose:** Continuously generates OpenAI embeddings (3072-dim, text-embedding-3-large) for chunks

**Mode:** Continuous (checks every 60s for chunks without embeddings)

**Monitoring:**
```bash
railway run python check_backlog.py
railway run python check_dims_simple.py
```

---

### 5. FTS Indexing Service (Continuous)
**Service ID:** `ffe65f79-4dc5-4757-b772-5a99c7ea624f`

**Environment Variables:**
```bash
SERVICE_MODE=fts-continuous
FTS_CONTINUOUS_INTERVAL=60
FTS_BATCH=100000
```

**Command:** `python main.py services start --services fts --fts-interval 60`

**Purpose:** Continuously maintains Full-Text Search (FTS) indexes using PostgreSQL tsvector for hybrid search

**Mode:** Continuous (checks every 60s for articles needing FTS indexing)

**Monitoring:**
```bash
railway link --service ffe65f79-4dc5-4757-b772-5a99c7ea624f
railway logs
```

---

## Pipeline Architecture

```
┌─────────────┐
│  RSS POLL   │ (Cron - scheduled)
│  (d116f9..) │
└──────┬──────┘
       │ Ingests articles to `raw` table
       ↓
┌─────────────┐
│    WORK     │ (Continuous - 30s interval)
│  (469223..) │ Monitors: status='pending' in `raw`
└──────┬──────┘
       │ Extracts fulltext, metadata → stores in `fulltext` table
       ├──────────────────────┐
       ↓                      ↓
┌─────────────┐      ┌─────────────┐
│   CHUNK     │      │  FTS Index  │ (Continuous - 60s interval)
│  (f32c12..) │      │  (ffe65f..) │ Monitors: articles without FTS
└──────┬──────┘      └─────────────┘
       │                      │ Creates tsvector indexes for fulltext search
       │ Creates semantic chunks → stores in `article_chunks`
       ↓
┌─────────────┐
│ OpenAIEmbed │ (Continuous - 60s interval)
│  (c015bd..) │ Monitors: chunks without embeddings
└─────────────┘
       │ Generates 3072-dim embeddings → updates `article_chunks.embedding`
       ↓
    Ready for hybrid search! (Semantic + FTS)
```

## Benefits of Continuous Architecture

✅ **Automatic Processing** - New articles processed without manual intervention
✅ **Low Latency** - Articles flow through pipeline within minutes
✅ **Resilient** - Each service restarts on failure (Railway policy)
✅ **Scalable** - Adjust batch sizes and intervals independently
✅ **Observable** - Each service reports backlog statistics

## Deployment

All services share the same repository and `railway.toml`:

```toml
[build]
builder = "nixpacks"

[deploy]
startCommand = "python launcher.py"
restartPolicyType = "on_failure"
restartPolicyMaxRetries = 10
```

**To deploy all services:**
```bash
# Push to GitHub (auto-deploys all services)
git push origin main

# Or deploy manually to specific service
railway link --service <SERVICE_ID>
railway up
```

## Testing Launcher

```bash
# Test all modes locally
python test_launcher_continuous.py

# Test on Railway
railway run python test_launcher_continuous.py
```

## Monitoring Commands

### Overall System Health
```bash
# Check all services status
railway link --project e2cb23db-1ef4-4511-92d0-66ff17499cce
railway service  # Select each service and check logs
```

### WORK Backlog
```bash
railway link --service 4692233a-27bd-4e1c-b4e2-142f7cc59601
railway run python -c "from services.work_continuous_service import WorkContinuousService; s = WorkContinuousService(); stats = s.get_backlog_stats(); print(f'Pending: {stats.get(\"pending\", 0):,}, Processed: {stats.get(\"processed\", 0):,}, Completion: {stats.get(\"completion\", 0)}%')"
```

### CHUNK Backlog
```bash
railway link --service f32c1205-d7e4-429b-85ea-e8b00d897334
railway run python -c "from services.chunk_continuous_service import ChunkContinuousService; s = ChunkContinuousService(); stats = s.get_backlog_stats(); print(f'Pending: {stats.get(\"pending_chunking\", 0):,}, Total chunks: {stats.get(\"total_chunks\", 0):,}, Completion: {stats.get(\"completion\", 0)}%')"
```

### Embedding Backlog
```bash
railway link --service c015bdb5-710d-46b8-ad86-c566b99e7560
railway run python check_backlog.py
```

## Environment Variables Reference

### Common Variables (All Services)
```bash
PG_DSN=postgresql://user:pass@host:port/db
ENABLE_LOCAL_CHUNKING=true
OLLAMA_BASE_URL=https://ollama.nexlify.solutions
OLLAMA_MODEL=qwen2.5-coder:3b
```

### WORK Service
```bash
SERVICE_MODE=work-continuous
WORK_CONTINUOUS_INTERVAL=30      # Seconds between checks
WORK_CONTINUOUS_BATCH=50         # Articles per batch
WORK_WORKERS=10                  # Concurrent workers
```

### CHUNK Service
```bash
SERVICE_MODE=chunk-continuous
CHUNK_CONTINUOUS_INTERVAL=30     # Seconds between checks
CHUNK_CONTINUOUS_BATCH=100       # Articles per batch
```

### OpenAI Embedding Service
```bash
SERVICE_MODE=openai-migration
MIGRATION_INTERVAL=60            # Seconds between checks
OPENAI_API_KEY=sk-proj-...
OPENAI_EMBEDDING_MODEL=text-embedding-3-large
OPENAI_EMBEDDING_BATCH_SIZE=100
OPENAI_EMBEDDING_MAX_RETRIES=3
EMBEDDING_TIMEOUT=30
```

### FTS Indexing Service
```bash
SERVICE_MODE=fts-continuous
FTS_CONTINUOUS_INTERVAL=60       # Seconds between checks
FTS_BATCH=100000                 # Articles per batch
```

## Current Status (2025-10-05)

✅ All services deployed with continuous architecture
✅ POLL: Cron-scheduled RSS feed polling (d116f94c)
✅ WORK: Continuous article processing - 30s interval (4692233a)
✅ CHUNK: Continuous chunking - 30s interval (f32c1205)
✅ OpenAIEmbending: Continuous embedding generation - 60s interval (c015bdb5)
✅ FTS Indexing: Continuous FTS indexing - 60s interval (ffe65f79)
✅ OpenAI embedding migration completed: 217,694/217,694 chunks (100%)
✅ All embeddings are 3072-dim (text-embedding-3-large)
✅ Hybrid search enabled: Semantic (pgvector) + Full-Text Search (tsvector)
✅ Fully automated pipeline - no manual intervention required
