-- Stage 6/7: FTS and Embeddings for article_chunks

-- Ensure pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Add FTS vector and embedding columns
ALTER TABLE article_chunks ADD COLUMN IF NOT EXISTS fts_vector tsvector;
ALTER TABLE article_chunks ADD COLUMN IF NOT EXISTS embedding vector;

-- Backfill FTS vector using simple config (language-specific configs can be used later)
UPDATE article_chunks SET fts_vector = to_tsvector('simple', coalesce(text, '')) WHERE fts_vector IS NULL;

-- Indexes
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes WHERE schemaname = 'public' AND indexname = 'ix_article_chunks_fts'
    ) THEN
        CREATE INDEX ix_article_chunks_fts ON article_chunks USING GIN (fts_vector);
    END IF;
END$$;

-- HNSW index on embedding (requires pgvector >= 0.5.0)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes WHERE schemaname = 'public' AND indexname = 'ix_article_chunks_embedding_hnsw'
    ) THEN
        CREATE INDEX ix_article_chunks_embedding_hnsw ON article_chunks USING hnsw (embedding vector_cosine_ops);
    END IF;
END$$;

