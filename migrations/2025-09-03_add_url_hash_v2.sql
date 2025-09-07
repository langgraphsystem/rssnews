-- 1) Add new column (nullable for backfill)
ALTER TABLE raw ADD COLUMN IF NOT EXISTS url_hash_v2 text;
ALTER TABLE articles_index ADD COLUMN IF NOT EXISTS url_hash_v2 text;

-- 2) Backfill url_hash_v2 from canonical URL (server-side function if exists) or copy legacy where possible
-- If you have a canonicalization function in DB, use it here; otherwise do application-side backfill.
-- Temporary: copy old url_hash as placeholder to reduce NULLs (will be corrected by application backfill)
UPDATE raw SET url_hash_v2 = url_hash WHERE url_hash_v2 IS NULL;
UPDATE articles_index SET url_hash_v2 = url_hash WHERE url_hash_v2 IS NULL;

-- 3) Create indexes (concurrently in production)
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS ux_raw_url_hash_v2 ON raw (url_hash_v2);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_articles_index_url_hash_v2 ON articles_index (url_hash_v2);

-- 4) (Optional later) Drop legacy unique if it conflicts; keep until cutover
-- DROP INDEX IF EXISTS ux_raw_url_hash;

-- 5) After backfill validation you can enforce NOT NULL:
-- ALTER TABLE raw ALTER COLUMN url_hash_v2 SET NOT NULL;
-- ALTER TABLE articles_index ALTER COLUMN url_hash_v2 SET NOT NULL;

