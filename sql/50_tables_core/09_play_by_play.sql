-- ============================================================
-- 09_play_by_play.sql
-- Play-by-play events (Retrosheet)
-- Schema: baseball
-- Mirrors: baseball.db.models.PlayByPlay
-- ============================================================

CREATE TABLE IF NOT EXISTS baseball.play_by_play (
    pbp_id              SERIAL          PRIMARY KEY,
    game_id             INTEGER         NOT NULL REFERENCES baseball.game(game_id),
    inning              INTEGER         NOT NULL,
    half_inning         VARCHAR(3)      NOT NULL,   -- top, bot
    batter_id           INTEGER         REFERENCES baseball.player(player_id),
    pitcher_id          INTEGER         REFERENCES baseball.player(player_id),
    sequence_number     INTEGER         NOT NULL,
    balls               INTEGER,
    strikes             INTEGER,
    outs_at_start       INTEGER,
    pitch_count         INTEGER,
    event_type          VARCHAR(100),
    event_code          VARCHAR(10),                -- Retrosheet event code
    runs_scored         INTEGER         DEFAULT 0,
    rbis                INTEGER         DEFAULT 0,
    home_score_after    INTEGER,
    away_score_after    INTEGER,
    raw_event_description TEXT,
    created_at          TIMESTAMP       NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS ix_pbp_game_id         ON baseball.play_by_play (game_id);
CREATE INDEX IF NOT EXISTS ix_pbp_game_inning     ON baseball.play_by_play (game_id, inning, half_inning);
CREATE INDEX IF NOT EXISTS ix_pbp_batter          ON baseball.play_by_play (batter_id);
CREATE INDEX IF NOT EXISTS ix_pbp_pitcher         ON baseball.play_by_play (pitcher_id);
