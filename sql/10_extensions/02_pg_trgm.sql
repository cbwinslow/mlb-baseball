-- 10_extensions/02_pg_trgm.sql
-- Enable pg_trgm for trigram-based similarity search on player/team names.

CREATE EXTENSION IF NOT EXISTS pg_trgm;
