# Data Contracts (pre‑RAG)

This document defines key tables used before/for RAG preparation.

## articles_index
| Field | Type | Notes |
|---|---|---|
| id | bigserial PK | |
| url_hash_v2 | text | SHA‑256(canonical_url), unique index |
| text_hash | text | SHA‑256(normalized text), unique index (conflict key) |
| title | text | Optional |
| author | text | Optional |
| source | text | Domain |
| first_seen | timestamptz | |
| last_seen | timestamptz | |

- Uniqueness: `text_hash` (primary dedup); `url_hash_v2` indexed for URL-level lookups
- Indexes: `(url_hash_v2)`, `(text_hash)`

## article_chunks
| Field | Type | Notes |
|---|---|---|
| id | bigserial PK | |
| chunk_id | text | Unique business key |
| article_id | text | FK to articles_index.article_id or equivalent |
| chunk_index | int | Position in article |
| text | text | Chunk content |
| word_count_chunk | int | |
| char_start | int | |
| char_end | int | |
| semantic_type | text | intro/body/list/conclusion |
| url | text | Denormalized |
| title_norm | text | Denormalized |
| source_domain | text | Denormalized |
| published_at | timestamptz | Denormalized |
| language | text | |
| category | text | Optional |
| tags_norm | jsonb | Default [] |
| created_at | timestamptz | |

- Uniqueness: `(article_id, chunk_index)`
- Indexes: `(article_id)`, `(source_domain, published_at DESC)`, `(language, category)`
- Optional FTS: GIN on `to_tsvector('simple', text)`

## article_embeddings
| Field | Type | Notes |
|---|---|---|
| id | bigserial PK | |
| chunk_id | text | FK to article_chunks.chunk_id (unique) |
| embedding | vector | pgvector |
| dim | int | Embedding dimensionality |
| model | text | e.g., `gemini-embedding-001` |
| created_at | timestamptz | |

- Uniqueness: `chunk_id`
- Recommended indexes: pgvector HNSW on `embedding` (e.g., `USING hnsw (embedding vector_cosine_ops)`)

Additional (article_chunks)
- fts_vector tsvector: to_tsvector('simple', text)
- embedding vector: populated by Stage 7 when EMBEDDING_MODEL is configured

