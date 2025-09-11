-- Resize pgvector embedding column for gemini-embedding-001 (3072 dims)
-- Run these statements in Railway → Postgres → SQL, step by step.

-- 1) Drop old embedding indexes if they exist (safe to run multiple times)
DROP INDEX IF EXISTS ix_article_chunks_embedding_hnsw;
DROP INDEX IF EXISTS ix_article_chunks_embedding_ivf;

-- 2) (Optional, but recommended if any old vectors exist)
-- Clear existing embeddings to avoid dimension mismatch after ALTER
UPDATE article_chunks SET embedding = NULL WHERE embedding IS NOT NULL;

-- 3) Change pgvector dimensions from 768 to 3072
ALTER TABLE article_chunks ALTER COLUMN embedding TYPE vector(3072);

-- 4) Create embedding index
-- Preferred (pgvector >= 0.5.0): HNSW
-- Uncomment ONE of the following index statements that matches your pgvector version

-- CREATE INDEX ix_article_chunks_embedding_hnsw
--   ON article_chunks USING hnsw (embedding vector_cosine_ops);

-- Fallback (older pgvector): IVFFLAT
-- CREATE INDEX ix_article_chunks_embedding_ivf
--   ON article_chunks USING ivfflat (embedding vector_cosine_ops);

-- Note: CREATE INDEX CONCURRENTLY is not used here because it cannot run inside a transaction
-- in some SQL consoles. If you execute by hand and want minimal locking, run the chosen
-- CREATE INDEX statement with the CONCURRENTLY keyword from a non-transactional session.

