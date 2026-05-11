-- ============================================================
-- 01_raw_mlbstatsapi.sql
-- Raw MLB StatsAPI payload storage
-- Schema: baseball
-- Mirrors: baseball.db.models.RawMlbstatsapi
-- ============================================================

CREATE TABLE IF NOT EXISTS baseball.raw_mlbstatsapi (
    raw_id              SERIAL          PRIMARY KEY,
    endpoint            VARCHAR(200)    NOT NULL,   -- /game/{id}, /people/{id}, etc.
    resource_id         VARCHAR(100),               -- game_pk, player_id, etc.
    payload             TEXT            NOT NULL,   -- JSON
    checksum            VARCHAR(64)     UNIQUE,     -- SHA256 of payload
    retrieved_at        TIMESTAMP       NOT NULL DEFAULT NOW(),
    created_at          TIMESTAMP       NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS ix_raw_mlb_retrieved     ON baseball.raw_mlbstatsapi (retrieved_at);
CREATE INDEX IF NOT EXISTS ix_raw_mlb_resource      ON baseball.raw_mlbstatsapi (resource_id);
CREATE INDEX IF NOT EXISTS ix_raw_mlb_endpoint_id   ON baseball.raw_mlbstatsapi (endpoint, resource_id);
