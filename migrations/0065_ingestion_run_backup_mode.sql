-- `mlb backup` starts recording itself in meta.ingestion_run (see backup.py),
-- so `mlb doctor` can reuse the existing check_recent_run helper to flag a
-- stale backup the same way it already flags a stale connector run, instead
-- of inventing a separate freshness mechanism for one operation.

ALTER TABLE meta.ingestion_run DROP CONSTRAINT ingestion_run_mode_check;
ALTER TABLE meta.ingestion_run ADD CONSTRAINT ingestion_run_mode_check
    CHECK (mode IN ('bootstrap', 'update', 'backfill', 'features', 'backup'));
