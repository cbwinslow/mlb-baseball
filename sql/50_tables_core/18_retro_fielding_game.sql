-- =============================================================
-- 18_retro_fielding_game.sql
-- Per-game fielding statistics from Retrosheet
-- Schema: baseball
-- Table:  retro_fielding_game
-- =============================================================

CREATE TABLE IF NOT EXISTS baseball.retro_fielding_game (

    -- Primary key
    fielding_game_id  BIGSERIAL PRIMARY KEY,

    -- Game / player context
    game_id           VARCHAR(12)   NOT NULL,
    player_id         VARCHAR(8)    NOT NULL,
    team_id           VARCHAR(3)    NOT NULL,
    season            SMALLINT      NOT NULL,
    game_date         DATE,
    home_flag         BOOLEAN,
    position          VARCHAR(2)    NOT NULL,  -- defensive position played
    seq               SMALLINT,               -- order if multiple positions in same game

    -- Standard fielding stats
    inn_outs          SMALLINT,               -- outs played at this position (inn * 3)
    po                SMALLINT      NOT NULL DEFAULT 0,  -- putouts
    a                 SMALLINT      NOT NULL DEFAULT 0,  -- assists
    e                 SMALLINT      NOT NULL DEFAULT 0,  -- errors
    dp                SMALLINT,                          -- double plays
    tp                SMALLINT,                          -- triple plays
    pb                SMALLINT,                          -- passed balls (catchers)
    xi                SMALLINT,                          -- interference
    sb_allowed        SMALLINT,                          -- stolen bases allowed (catchers)
    cs_made           SMALLINT,                          -- caught stealing (catchers)

    -- Source metadata
    source_file       VARCHAR(64),
    created_at        TIMESTAMPTZ   NOT NULL DEFAULT now()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_retro_fld_g_season
    ON baseball.retro_fielding_game (season);
CREATE INDEX IF NOT EXISTS idx_retro_fld_g_player
    ON baseball.retro_fielding_game (player_id);
CREATE INDEX IF NOT EXISTS idx_retro_fld_g_team_season
    ON baseball.retro_fielding_game (team_id, season);
CREATE INDEX IF NOT EXISTS idx_retro_fld_g_game
    ON baseball.retro_fielding_game (game_id);
CREATE UNIQUE INDEX IF NOT EXISTS uidx_retro_fld_g_player_game_pos_seq
    ON baseball.retro_fielding_game (game_id, player_id, position, seq);
