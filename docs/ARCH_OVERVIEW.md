# Architecture Overview

Flow (text diagram)
- discovery (optional)
  -> poll (raw.pending)
  -> work/pipeline (Stages 1–8)
  -> index/chunks
  -> embeddings

Where components are used
- PostgreSQL: feeds, raw, articles_index, diagnostics
- Redis: queue/locks/rate‑limits (recommended for retry/backpressure)
- LLMs: Stage 6 refinement (Gemini 2.5 Flash), Stage 7 embeddings (Gemini Embedding‑001)
  - Stage 6: deterministic chunking → selective LLM refine (<= LLM_MAX_SHARE)
  - Stage 7: FTS vector (to_tsvector) + embeddings (pgvector)

Related docs
- Goals & Scope: docs/GOALS_AND_SCOPE.md
- Data Contracts: docs/DATA_CONTRACTS.md
