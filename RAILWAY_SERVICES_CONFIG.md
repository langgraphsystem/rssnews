# Railway Multi-Service Configuration

## Overview

Project uses `launcher.py` with `railway.toml` for multi-service deployment. Each service runs different commands based on `SERVICE_MODE` environment variable.

## Services Configuration

### 1. RSS POLL Service
**Service ID:** `d116f94c-c0f7-4712-82a8-283258d05de4`

**Environment Variables:**
```bash
SERVICE_MODE=poll
POLL_WORKERS=10
POLL_BATCH=10
```

**Command:** `python main.py poll --workers 10 --batch-size 10`

**Purpose:** Polls RSS feeds and ingests new articles into database

---

### 2. WORK Service
**Service ID:** `4692233a-27bd-4e1c-b4e2-142f7cc59601`

**Environment Variables:**
```bash
SERVICE_MODE=work
WORK_WORKERS=10
WORK_BATCH=50
WORK_SIMPLIFIED=false
```

**Command:** `python main.py work --workers 10 --batch-size 50`

**Purpose:** Processes raw articles (fulltext extraction, NLP, metadata enrichment)

---

### 3. CHUNK Service
**Service ID:** `f32c1205-d7e4-429b-85ea-e8b00d897334`

**Environment Variables:**
```bash
SERVICE_MODE=chunking
CHUNKING_BATCH=100
```

**Command:** `python main.py services run-once --services chunking --chunking-batch 100`

**Purpose:** Chunks processed articles using Qwen2.5-coder via Ollama

---

### 4. OpenAIEmbending Service
**Service ID:** `c015bdb5-710d-46b8-ad86-c566b99e7560`

**Environment Variables:**
```bash
SERVICE_MODE=openai-migration
MIGRATION_INTERVAL=60
OPENAI_API_KEY=sk-proj-...
OPENAI_EMBEDDING_MODEL=text-embedding-3-large
OPENAI_EMBEDDING_BATCH_SIZE=100
```

**Command:** `python services/openai_embedding_migration_service.py continuous --interval 60`

**Purpose:** Continuous background processing - generates OpenAI embeddings (3072-dim) for chunks

---

## Architecture

```
launcher.py (reads SERVICE_MODE)
    ↓
RSS POLL → ingests articles to `raw` table
    ↓
WORK → processes articles, enriches metadata
    ↓
CHUNK → creates chunks (no embeddings)
    ↓
OpenAIEmbending → adds embeddings to chunks (continuous background process)
```

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
# Deploy to each service
railway link --service <SERVICE_ID>
railway up

# Or use GitHub auto-deploy (recommended)
git push origin main
```

## Testing Launcher

```bash
# Test command generation locally
python test_launcher.py

# Test on Railway
railway run python test_launcher.py
```

## Monitoring

Check service status:
```bash
railway link --service <SERVICE_ID>
railway logs
```

Check embedding migration progress:
```bash
railway run python check_backlog.py
```

## Current Status (2025-10-03)

✅ All services deployed with correct `SERVICE_MODE`
✅ OpenAI embedding migration completed: 209,415/209,415 chunks (100%)
✅ All embeddings are 3072-dim (text-embedding-3-large)
✅ Continuous embedding processing active (60-second interval)
