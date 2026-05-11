-- =============================================================
-- 17_retro_pitching_game.sql
-- Per-game pitching statistics from Retrosheet
-- Schema: baseball
-- Table:  retro_pitching_game
-- =============================================================

CREATE TABLE IF NOT EXISTS baseball.retro_pitching_game (

    -- Primary key
    pitching_game_id  BIGSERIAL PRIMARY KEY,

    -- Game / player context
    game_id           VARCHAR(12)   NOT NULL,
    player_id         VARCHAR(8)    NOT NULL,
    team_id           VARCHAR(3)    NOT NULL,
    season            SMALLINT      NOT NULL,
    game_date         DATE,
    home_flag         BOOLEAN,
    seq               SMALLINT,                -- appearance order in game (1=starter)

    -- Win/loss/save flags
    win_flag          BOOLEAN,
    loss_flag         BOOLEAN,
    save_flag         BOOLEAN,
    complete_game     BOOLEAN,
    shutout           BOOLEAN,

    -- Standard pitching stats
    ip_outs           SMALLINT      NOT NULL DEFAULT 0,  -- outs recorded (IP * 3)
    bf                SMALLINT,                          -- batters faced
    ab                SMALLINT,
    h                 SMALLINT      NOT NULL DEFAULT 0,
    doubles           SMALLINT,
    triples           SMALLINT,
    hr                SMALLINT      NOT NULL DEFAULT 0,
    r                 SMALLINT      NOT NULL DEFAULT 0,  -- runs allowed
    er                SMALLINT      NOT NULL DEFAULT 0,  -- earned runs
    bb                SMALLINT      NOT NULL DEFAULT 0,
    ibb               SMALLINT,
    so                SMALLINT      NOT NULL DEFAULT 0,
    hbp               SMALLINT,
    wp                SMALLINT,                          -- wild pitches
    bk                SMALLINT,                          -- balks
    sh                SMALLINT,
    sf                SMALLINT,
    gdp               SMALLINT,
    pitches           SMALLINT,
    strikes           SMALLINT,

    -- Source metadata
    source_file       VARCHAR(64),
    created_at        TIMESTAMPTZ   NOT NULL DEFAULT now()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_retro_pit_g_season
    ON baseball.retro_pitching_game (season);
CREATE INDEX IF NOT EXISTS idx_retro_pit_g_player
    ON baseball.retro_pitching_game (player_id);
CREATE INDEX IF NOT EXISTS idx_retro_pit_g_team_season
    ON baseball.retro_pitching_game (team_id, season);
CREATE INDEX IF NOT EXISTS idx_retro_pit_g_game
    ON baseball.retro_pitching_game (game_id);
CREATE UNIQUE INDEX IF NOT EXISTS uidx_retro_pit_g_player_game_seq
    ON baseball.retro_pitching_game (game_id, player_id, seq);
