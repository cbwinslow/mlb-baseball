-- ============================================================
-- 04_raw_fangraphs.sql
-- Raw FanGraphs data payload storage
-- Schema: baseball
-- Mirrors: baseball.db.models.RawFangraphs
-- ============================================================

CREATE TABLE IF NOT EXISTS baseball.raw_fangraphs (
    raw_id              SERIAL          PRIMARY KEY,
    data_type           VARCHAR(50)     NOT NULL,   -- batting, pitching, fielding
    season              INTEGER         NOT NULL,
    resource_id         VARCHAR(100),               -- player_id
    payload             TEXT            NOT NULL,   -- JSON or CSV
    checksum            VARCHAR(64)     UNIQUE,     -- SHA256 of payload
    retrieved_at        TIMESTAMP       NOT NULL DEFAULT NOW(),
    created_at          TIMESTAMP       NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS ix_raw_fg_season         ON baseball.raw_fangraphs (season);
CREATE INDEX IF NOT EXISTS ix_raw_fg_resource        ON baseball.raw_fangraphs (resource_id);
CREATE INDEX IF NOT EXISTS ix_raw_fg_season_type     ON baseball.raw_fangraphs (season, data_type);
