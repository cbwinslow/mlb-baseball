-- ============================================================
-- 01_ingest_log.sql
-- Track all data ingestion operations
-- Schema: baseball
-- Mirrors: baseball.db.models.IngestLog
-- ============================================================

CREATE TABLE IF NOT EXISTS baseball.ingest_log (
    log_id              SERIAL          PRIMARY KEY,
    source              VARCHAR(50)     NOT NULL,
    endpoint_or_file    VARCHAR(200)    NOT NULL,
    season              INTEGER,
    rows_processed      INTEGER         NOT NULL DEFAULT 0,
    rows_inserted       INTEGER         NOT NULL DEFAULT 0,
    rows_updated        INTEGER         NOT NULL DEFAULT 0,
    rows_skipped        INTEGER         NOT NULL DEFAULT 0,
    status              VARCHAR(20)     NOT NULL,
    error_message       TEXT,
    started_at          TIMESTAMP       NOT NULL,
    completed_at        TIMESTAMP,
    duration_seconds    INTEGER
);

CREATE INDEX IF NOT EXISTS ix_ingest_log_source      ON baseball.ingest_log (source);
CREATE INDEX IF NOT EXISTS ix_ingest_log_source_date ON baseball.ingest_log (source, started_at);
CREATE INDEX IF NOT EXISTS ix_ingest_log_season      ON baseball.ingest_log (season);
CREATE INDEX IF NOT EXISTS ix_ingest_log_status      ON baseball.ingest_log (status);
