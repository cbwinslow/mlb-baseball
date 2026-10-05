-- Odds capture (openspec/changes/odds-history-capture) records each 15-minute
-- Kalshi/Polymarket snapshot run in the existing run ledger with mode
-- 'snapshot', so capture gaps and failures are visible to `mlb doctor`.

ALTER TABLE meta.ingestion_run DROP CONSTRAINT ingestion_run_mode_check;
ALTER TABLE meta.ingestion_run ADD CONSTRAINT ingestion_run_mode_check
    CHECK (mode IN (
        'bootstrap', 'update', 'backfill', 'features', 'backup', 'nightly', 'snapshot'
    ));
