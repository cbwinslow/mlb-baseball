-- ============================================================
-- 02_validation_log.sql
-- Track data validation runs
-- Schema: baseball
-- Mirrors: baseball.db.models.ValidationLog
-- ============================================================

CREATE TABLE IF NOT EXISTS baseball.validation_log (
    log_id              SERIAL          PRIMARY KEY,
    check_name          VARCHAR(100)    NOT NULL,
    table_name          VARCHAR(100)    NOT NULL,
    status              VARCHAR(20)     NOT NULL,   -- passed, failed, warning
    row_count           INTEGER,
    issue_count         INTEGER         NOT NULL DEFAULT 0,
    issue_description   TEXT,
    checked_at          TIMESTAMP       NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_validation_check_name  ON baseball.validation_log (check_name);
CREATE INDEX IF NOT EXISTS ix_validation_table       ON baseball.validation_log (table_name);
CREATE INDEX IF NOT EXISTS ix_validation_status      ON baseball.validation_log (status);
CREATE INDEX IF NOT EXISTS ix_validation_check_date  ON baseball.validation_log (check_name, checked_at);
