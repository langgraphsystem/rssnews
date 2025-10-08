-- Migration: Add source_query column to user_interactions table if missing
-- This column stores the search query that led to user interactions

-- Check if column exists and add if missing
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'user_interactions'
        AND column_name = 'source_query'
    ) THEN
        ALTER TABLE user_interactions
        ADD COLUMN source_query TEXT;

        RAISE NOTICE 'Added source_query column to user_interactions table';
    ELSE
        RAISE NOTICE 'source_query column already exists in user_interactions table';
    END IF;
END $$;

-- Verify the column exists
SELECT
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_name = 'user_interactions'
ORDER BY ordinal_position;
