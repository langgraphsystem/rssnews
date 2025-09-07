# Goals & Scope

## Mission
Process RSS feeds into normalized, deduplicated, and enriched article data to prepare high‑quality inputs for a downstream RAG (Retrieval‑Augmented Generation) system (indexing, chunking, and embeddings) with predictable latency and reliability.

## In‑Scope
- RSS feed discovery, polling with conditional GET (ETag/Last‑Modified)
- Normalization (canonical URLs), content extraction, metadata enrichment
- Deduplication by URL/text hashes, indexing into articles_index
- Diagnostics/logging, minimal retry/backoff for HTTP
- Pre‑RAG preparation: chunks and embeddings handoff interfaces

## Out‑of‑Scope
- Full‑text search UI, dashboards, or end‑user applications
- Editorial quality curation and manual moderation workflows
- Advanced anti‑bot/anti‑paywall circumvention beyond basic handling
- Long‑term storage lifecycle policies and legal retention
- Authentication/authorization for external consumers

## Non‑Functional Requirements
- Throughput: scalable to tens of thousands of articles/hour
- Concurrency: multi‑threaded workers; horizontally scalable
- Latency SLO: p99 ≤ 5s per batch
- Availability SLA: 99.9%
- Error rate: < 1% sustained (excluding source 4xx)

## LLM Participation
- Stage 6 (refining): Gemini 2.5 Flash, applied to ≤ 30% статей (LLM budget share)
- Stage 7 (embeddings): Gemini Embedding‑001 for vectorization

## Data Contracts
See docs/DATA_CONTRACTS.md

## Risks / Constraints
- LLM rate limits/cost ceilings; enforce LLM_MAX_SHARE
- DB/Redis sizing and connection limits under burst loads
- Source variability (RSS format drift, paywalls, JS‑heavy sites)
- Network egress restrictions and per‑domain rate limits
