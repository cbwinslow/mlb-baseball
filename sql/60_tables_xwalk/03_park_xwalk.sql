-- ============================================================
-- 03_park_xwalk.sql
-- Park/Stadium ID crosswalk across all data sources
-- Schema: baseball
-- Mirrors: baseball.db.models.ParkXwalk
-- ============================================================

CREATE TABLE IF NOT EXISTS baseball.park_xwalk (
    xwalk_id            SERIAL          PRIMARY KEY,
    park_id             INTEGER         NOT NULL REFERENCES baseball.park(park_id),
    mlbam_id            INTEGER         UNIQUE,
    retrosheet_id       VARCHAR(10)     UNIQUE,
    bbref_id            VARCHAR(50)     UNIQUE,
    created_at          TIMESTAMP       NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMP       NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS ix_park_xwalk_park_id    ON baseball.park_xwalk (park_id);
CREATE INDEX IF NOT EXISTS ix_park_xwalk_mlbam      ON baseball.park_xwalk (mlbam_id);
CREATE INDEX IF NOT EXISTS ix_park_xwalk_retrosheet ON baseball.park_xwalk (retrosheet_id);
CREATE INDEX IF NOT EXISTS ix_park_xwalk_bbref      ON baseball.park_xwalk (bbref_id);
