# Configuration Reference

| Variable | Purpose |
|---|---|
| PG_DSN | PostgreSQL DSN for core pipeline components |
| REDIS_URL | Redis connection URL for queues/locks/rate‑limits |
| GEMINI_API_KEY | API key for Gemini LLM/embeddings |
| CHUNK_LLM_MODEL | Model for Stage 6 refining (e.g., gemini-2.5-flash) |
| EMBEDDING_MODEL | Model for embeddings (e.g., gemini-embedding-001) |
| LLM_MAX_SHARE | Max fraction of items allowed to use LLM (e.g., 0.3) |
| BATCH_SIZE_DEFAULT | Default batch size for workers |
| BATCH_SIZE_MIN | Minimum allowed batch size |
| BATCH_SIZE_MAX | Maximum allowed batch size |
| SLO_BATCH_P99_SEC | SLO target for batch p99 latency (seconds) |
| SLA_AVAILABILITY | Target availability percentage (e.g., 99.9) |
| LOG_LEVEL | Logging level (DEBUG/INFO/WARNING/ERROR) |

Related files
- .env.example
- docs/GOALS_AND_SCOPE.md
- docs/SLO_SLA.md
