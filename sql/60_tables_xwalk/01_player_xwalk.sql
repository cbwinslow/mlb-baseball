-- ============================================================
-- 01_player_xwalk.sql
-- Player ID crosswalk across all data sources
-- Schema: baseball
-- Mirrors: baseball.db.models.PlayerXwalk
-- ============================================================

CREATE TABLE IF NOT EXISTS baseball.player_xwalk (
    xwalk_id            SERIAL          PRIMARY KEY,
    player_id           INTEGER         NOT NULL REFERENCES baseball.player(player_id),
    mlbam_id            INTEGER         UNIQUE,
    retrosheet_id       VARCHAR(20)     UNIQUE,
    lahman_id           VARCHAR(20)     UNIQUE,
    fangraphs_id        INTEGER         UNIQUE,
    bbref_id            VARCHAR(50)     UNIQUE,
    created_at          TIMESTAMP       NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMP       NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS ix_player_xwalk_player_id    ON baseball.player_xwalk (player_id);
CREATE INDEX IF NOT EXISTS ix_player_xwalk_mlbam        ON baseball.player_xwalk (mlbam_id);
CREATE INDEX IF NOT EXISTS ix_player_xwalk_retrosheet   ON baseball.player_xwalk (retrosheet_id);
CREATE INDEX IF NOT EXISTS ix_player_xwalk_fangraphs    ON baseball.player_xwalk (fangraphs_id);
CREATE INDEX IF NOT EXISTS ix_player_xwalk_bbref        ON baseball.player_xwalk (bbref_id);
