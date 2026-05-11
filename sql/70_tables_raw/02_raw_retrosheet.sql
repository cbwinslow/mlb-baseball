-- ============================================================
-- 02_raw_retrosheet.sql
-- Raw Retrosheet data file payload storage
-- Schema: baseball
-- Mirrors: baseball.db.models.RawRetrosheet
-- ============================================================

CREATE TABLE IF NOT EXISTS baseball.raw_retrosheet (
    raw_id              SERIAL          PRIMARY KEY,
    file_type           VARCHAR(50)     NOT NULL,   -- event, roster, schedule
    season              INTEGER         NOT NULL,
    game_date           DATE,
    game_id             VARCHAR(50),
    file_name           VARCHAR(200)    NOT NULL,
    payload             TEXT            NOT NULL,
    checksum            VARCHAR(64)     UNIQUE,     -- SHA256 of payload
    source_url          VARCHAR(500),
    retrieved_at        TIMESTAMP       NOT NULL DEFAULT NOW(),
    created_at          TIMESTAMP       NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS ix_raw_retro_season      ON baseball.raw_retrosheet (season);
CREATE INDEX IF NOT EXISTS ix_raw_retro_game_id     ON baseball.raw_retrosheet (game_id);
CREATE INDEX IF NOT EXISTS ix_raw_retro_season_type ON baseball.raw_retrosheet (season, file_type);
