# Railway Multi-Service Layout

This repository supports two patterns for Railway services:

1) Separate folders with service-specific `railway.toml` files (Root Directory per service):

- `services/poll/railway.toml` → `python main.py poll --workers 10 --batch-size 10`
- `services/work/railway.toml` → `python main.py work --workers 10 --batch-size 50`
- `services/embedding/railway.toml` → `python main.py services run-once --services embedding --embedding-batch 1000`
- `services/openai-migration/railway.toml` → `python services/openai_embedding_migration_service.py continuous --interval 60`

2) Single root with universal launcher (default):
   - Root `railway.toml` now runs `python launcher.py`.
   - Set per-service env var `SERVICE_MODE` to select the role:
     - `poll` → `python main.py poll --workers $POLL_WORKERS --batch-size $POLL_BATCH`
     - `work` → `python main.py work [--simplified] --workers $WORK_WORKERS --batch-size $WORK_BATCH`
     - `embedding` → `python main.py services run-once --services embedding --embedding-batch $EMBEDDING_BATCH`
     - `chunking` → `python main.py services run-once --services chunking --chunking-batch $CHUNKING_BATCH`
     - `openai-migration` → `python services/openai_embedding_migration_service.py continuous --interval $MIGRATION_INTERVAL`

Important:
- If Root Directory is the repo root, prefer the launcher pattern and set `SERVICE_MODE` per service in Railway.
- If you set Root Directory to the subfolder, the subfolder `railway.toml` applies to that service.
- Poll/Work/Embedding are local-only (Ollama). The OpenAI migration service requires `OPENAI_API_KEY`.

Environment hints (typical):
- Local LLM: `ENABLE_LOCAL_CHUNKING=true`, `ENABLE_LOCAL_EMBEDDINGS=true`, `OLLAMA_BASE_URL`, `OLLAMA_MODEL=qwen2.5-coder:3b`, `EMBEDDING_MODEL=embeddinggemma`.
- OpenAI migration: `OPENAI_API_KEY`, `OPENAI_EMBEDDING_MODEL=text-embedding-3-large`.
