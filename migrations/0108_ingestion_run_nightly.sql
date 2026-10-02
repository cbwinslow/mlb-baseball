-- `mlb nightly` supervises the daily steps and records one meta.ingestion_run
-- row per step attempt (mode 'nightly'), so duration and retry history live in
-- the existing run ledger instead of a second table. `attempt` is 1 for a first
-- try and counts up for each retry of the same step in one night.

ALTER TABLE meta.ingestion_run ADD COLUMN attempt integer NOT NULL DEFAULT 1;
ALTER TABLE meta.ingestion_run ADD CONSTRAINT ingestion_run_attempt_check
    CHECK (attempt >= 1);

ALTER TABLE meta.ingestion_run DROP CONSTRAINT ingestion_run_mode_check;
ALTER TABLE meta.ingestion_run ADD CONSTRAINT ingestion_run_mode_check
    CHECK (mode IN ('bootstrap', 'update', 'backfill', 'features', 'backup', 'nightly'));
