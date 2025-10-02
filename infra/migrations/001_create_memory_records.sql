-- Migration: Create memory_records table with pgvector support
-- Phase 3: Long-term Memory
-- Date: 2025-10-01

-- Enable pgvector extension (requires superuser or extension pre-installed)
CREATE EXTENSION IF NOT EXISTS vector;

-- Create memory_records table
CREATE TABLE IF NOT EXISTS memory_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    type VARCHAR(32) NOT NULL CHECK (type IN ('episodic', 'semantic')),
    content TEXT NOT NULL,
    embedding vector(1536),  -- OpenAI text-embedding-3-small dimension
    importance FLOAT NOT NULL DEFAULT 0.5 CHECK (importance BETWEEN 0.0 AND 1.0),
    ttl_days INTEGER NOT NULL DEFAULT 90,
    expires_at TIMESTAMP,
    refs TEXT[],  -- Array of article IDs or URLs
    user_id VARCHAR(128),  -- For multi-tenant support
    tags TEXT[],  -- Optional tags for categorization
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    accessed_at TIMESTAMP NOT NULL DEFAULT NOW(),
    access_count INTEGER NOT NULL DEFAULT 0,
    metadata JSONB DEFAULT '{}'
);

-- Create indexes
CREATE INDEX idx_memory_records_type ON memory_records(type);
CREATE INDEX idx_memory_records_user_id ON memory_records(user_id);
CREATE INDEX idx_memory_records_created_at ON memory_records(created_at);
CREATE INDEX idx_memory_records_expires_at ON memory_records(expires_at);
CREATE INDEX idx_memory_records_tags ON memory_records USING GIN(tags);

-- Create vector similarity index (IVFFlat for approximate nearest neighbor search)
-- Note: Build index after inserting initial data for better performance
CREATE INDEX idx_memory_records_embedding ON memory_records
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- Create function to auto-update expires_at based on ttl_days
CREATE OR REPLACE FUNCTION update_memory_expires_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.expires_at = NEW.created_at + (NEW.ttl_days || ' days')::INTERVAL;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger to auto-update expires_at
CREATE TRIGGER trigger_memory_expires_at
    BEFORE INSERT OR UPDATE OF ttl_days, created_at
    ON memory_records
    FOR EACH ROW
    EXECUTE FUNCTION update_memory_expires_at();

-- Create function to clean up expired memories
CREATE OR REPLACE FUNCTION cleanup_expired_memories()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM memory_records
    WHERE expires_at < NOW();

    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- Create function to update access tracking
CREATE OR REPLACE FUNCTION update_memory_access()
RETURNS TRIGGER AS $$
BEGIN
    NEW.accessed_at = NOW();
    NEW.access_count = NEW.access_count + 1;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Note: Access tracking trigger should be enabled only for UPDATE operations
-- and only when explicitly requested (to avoid overhead on bulk operations)

-- Grant permissions (adjust role as needed)
-- GRANT SELECT, INSERT, UPDATE, DELETE ON memory_records TO your_app_role;

-- Comments
COMMENT ON TABLE memory_records IS 'Long-term memory storage for Phase 3 with vector embeddings';
COMMENT ON COLUMN memory_records.type IS 'Memory type: episodic (events/facts) or semantic (concepts/relationships)';
COMMENT ON COLUMN memory_records.embedding IS 'Vector embedding for semantic search (1536-dim for OpenAI text-embedding-3-small)';
COMMENT ON COLUMN memory_records.importance IS 'Importance score [0.0, 1.0] for prioritization and expiration';
COMMENT ON COLUMN memory_records.ttl_days IS 'Time-to-live in days before automatic expiration';
COMMENT ON COLUMN memory_records.refs IS 'References to source articles (IDs or URLs)';
COMMENT ON COLUMN memory_records.user_id IS 'User ID for multi-tenant memory isolation';
COMMENT ON COLUMN memory_records.tags IS 'Tags for categorization and filtering';
