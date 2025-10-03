# Railway Multi-Service Layout

This repository uses separate folders for service-specific `railway.toml` files:

- `services/poll/railway.toml` → `python main.py poll --workers 10 --batch-size 10`
- `services/work/railway.toml` → `python main.py work --workers 10 --batch-size 50`
- `services/embedding/railway.toml` → `python main.py services run-once --services embedding --embedding-batch 1000`
- `services/openai-migration/railway.toml` → `python services/openai_embedding_migration_service.py continuous --interval 60`

Important:
- In Railway, set each service's Root Directory to the corresponding folder OR override the Start Command in the dashboard.
- If you set Root Directory to the subfolder, ensure the build context still includes project code (repo root). Otherwise override Start Command while keeping Root Directory at the repo root.
- Poll/Work/Embedding are local-only (Ollama). The OpenAI migration service requires `OPENAI_API_KEY`.

Environment hints:
- Local LLM: `ENABLE_LOCAL_CHUNKING=true`, `ENABLE_LOCAL_EMBEDDINGS=true`, `OLLAMA_BASE_URL`, `OLLAMA_MODEL=qwen2.5-coder:3b`, `EMBEDDING_MODEL=embeddinggemma`.
- OpenAI migration: `OPENAI_API_KEY`, `OPENAI_EMBEDDING_MODEL=text-embedding-3-large`.
