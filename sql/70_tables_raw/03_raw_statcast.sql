-- ============================================================
-- 03_raw_statcast.sql
-- Raw Statcast/Baseball Savant payload storage
-- Schema: baseball
-- Mirrors: baseball.db.models.RawStatcast
-- ============================================================

CREATE TABLE IF NOT EXISTS baseball.raw_statcast (
    raw_id              SERIAL          PRIMARY KEY,
    game_date           DATE            NOT NULL,
    season              INTEGER         NOT NULL,
    game_id             VARCHAR(50),
    play_id             VARCHAR(50)     UNIQUE,     -- Statcast play ID
    payload             TEXT            NOT NULL,   -- JSON
    checksum            VARCHAR(64)     UNIQUE,     -- SHA256 of payload
    retrieved_at        TIMESTAMP       NOT NULL DEFAULT NOW(),
    created_at          TIMESTAMP       NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS ix_raw_statcast_game_date ON baseball.raw_statcast (game_date);
CREATE INDEX IF NOT EXISTS ix_raw_statcast_season    ON baseball.raw_statcast (season);
CREATE INDEX IF NOT EXISTS ix_raw_statcast_game_id   ON baseball.raw_statcast (game_id);
CREATE INDEX IF NOT EXISTS ix_raw_statcast_game      ON baseball.raw_statcast (game_date, game_id);
