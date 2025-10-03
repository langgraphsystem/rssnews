-- Migration: Update memory embeddings to 3072 dimensions
-- Requires: pgvector extension present

-- Update memory_records embedding column to vector(3072)
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'memory_records' AND column_name = 'embedding'
  ) THEN
    BEGIN
      ALTER TABLE public.memory_records
      ALTER COLUMN embedding TYPE vector(3072);
    EXCEPTION WHEN others THEN
      RAISE NOTICE 'Altering memory_records.embedding to vector(3072) failed: %', SQLERRM;
    END;
  END IF;
END$$;

-- Recreate vector index to align with new dimension (if existed)
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM pg_indexes WHERE schemaname = 'public' AND indexname = 'idx_memory_records_embedding'
  ) THEN
    BEGIN
      DROP INDEX public.idx_memory_records_embedding;
    EXCEPTION WHEN others THEN
      RAISE NOTICE 'Dropping idx_memory_records_embedding failed: %', SQLERRM;
    END;
  END IF;
  BEGIN
    CREATE INDEX IF NOT EXISTS idx_memory_records_embedding ON public.memory_records
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
  EXCEPTION WHEN others THEN
    RAISE NOTICE 'Creating idx_memory_records_embedding failed: %', SQLERRM;
  END;
END$$;

-- Update view active_memory_records to ensure compatibility (no schema change needed)
-- No action required unless the view references dimension-specific functions (it does not).

