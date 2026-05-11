-- =============================================================
-- 16_retro_batting_game.sql
-- Per-game batting statistics from Retrosheet
-- Schema: baseball
-- Table:  retro_batting_game
-- =============================================================

CREATE TABLE IF NOT EXISTS baseball.retro_batting_game (

    -- Primary key
    batting_game_id   BIGSERIAL PRIMARY KEY,

    -- Game / player context
    game_id           VARCHAR(12)   NOT NULL,  -- Retrosheet game ID
    player_id         VARCHAR(8)    NOT NULL,  -- Retrosheet player ID
    team_id           VARCHAR(3)    NOT NULL,
    season            SMALLINT      NOT NULL,
    game_date         DATE,
    batting_order     SMALLINT,                -- 1-9
    position          VARCHAR(2),
    home_flag         BOOLEAN,

    -- Standard batting stats
    ab                SMALLINT      NOT NULL DEFAULT 0,  -- at-bats
    r                 SMALLINT      NOT NULL DEFAULT 0,  -- runs
    h                 SMALLINT      NOT NULL DEFAULT 0,  -- hits
    tb                SMALLINT,                          -- total bases
    doubles           SMALLINT      NOT NULL DEFAULT 0,
    triples           SMALLINT      NOT NULL DEFAULT 0,
    hr                SMALLINT      NOT NULL DEFAULT 0,  -- home runs
    rbi               SMALLINT      NOT NULL DEFAULT 0,  -- runs batted in
    bb                SMALLINT      NOT NULL DEFAULT 0,  -- walks
    ibb               SMALLINT,                          -- intentional walks
    so                SMALLINT      NOT NULL DEFAULT 0,  -- strikeouts
    hbp               SMALLINT,                          -- hit by pitch
    sh                SMALLINT,                          -- sacrifice hits
    sf                SMALLINT,                          -- sacrifice flies
    gdp               SMALLINT,                          -- grounded into double play
    sb                SMALLINT      NOT NULL DEFAULT 0,  -- stolen bases
    cs                SMALLINT,                          -- caught stealing
    pa                SMALLINT,                          -- plate appearances

    -- Source metadata
    source_file       VARCHAR(64),
    created_at        TIMESTAMPTZ   NOT NULL DEFAULT now()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_retro_bat_g_season
    ON baseball.retro_batting_game (season);
CREATE INDEX IF NOT EXISTS idx_retro_bat_g_player
    ON baseball.retro_batting_game (player_id);
CREATE INDEX IF NOT EXISTS idx_retro_bat_g_team_season
    ON baseball.retro_batting_game (team_id, season);
CREATE INDEX IF NOT EXISTS idx_retro_bat_g_game
    ON baseball.retro_batting_game (game_id);
CREATE UNIQUE INDEX IF NOT EXISTS uidx_retro_bat_g_player_game
    ON baseball.retro_batting_game (game_id, player_id);
