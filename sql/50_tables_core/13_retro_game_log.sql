-- ============================================================
-- 13_retro_game_log.sql
-- Retrosheet game log summary table (GLyyyy.TXT files)
-- One row per game with ~161 Retrosheet game log fields.
-- Schema: baseball
-- Mirrors: baseball.sources.retrosheet.models.RetroGameLog
-- Reference: https://www.retrosheet.org/gamelogs/glfields.txt
-- ============================================================

CREATE TABLE IF NOT EXISTS baseball.retro_game_log (
    id                  BIGSERIAL       PRIMARY KEY,

    -- Game identification
    game_id             VARCHAR(12)     NOT NULL UNIQUE,  -- e.g. NYA202304060
    game_date           DATE            NOT NULL,
    season              SMALLINT        NOT NULL,
    day_of_week         VARCHAR(3),                 -- Mon, Tue, ...
    game_number         SMALLINT        DEFAULT 0,  -- 0=single, 1=first of DH, 2=second

    -- Teams
    visiting_team       VARCHAR(3)      NOT NULL,
    visiting_league     VARCHAR(2),
    visiting_game_num   SMALLINT,                   -- game number in season for visitor
    home_team           VARCHAR(3)      NOT NULL,
    home_league         VARCHAR(2),
    home_game_num       SMALLINT,                   -- game number in season for home

    -- Score
    visiting_score      SMALLINT,
    home_score          SMALLINT,
    game_length_outs    SMALLINT,                   -- length in outs (normally 54)
    day_night           CHAR(1),                    -- D=day, N=night
    completion_info     VARCHAR(50),                -- completion game info if applicable
    forfeit_info        CHAR(1),                    -- V=visitor forfeit, H=home forfeit
    protest_info        CHAR(1),                    -- P=protested game

    -- Park
    park_id             VARCHAR(5),
    attendance          INTEGER,
    game_duration_min   SMALLINT,                   -- duration in minutes

    -- Line scores (runs per inning, comma-separated)
    visiting_line_score TEXT,
    home_line_score     TEXT,

    -- Visiting team totals
    visiting_ab         SMALLINT,
    visiting_h          SMALLINT,
    visiting_2b         SMALLINT,
    visiting_3b         SMALLINT,
    visiting_hr         SMALLINT,
    visiting_rbi        SMALLINT,
    visiting_sh         SMALLINT,   -- sacrifice hits
    visiting_sf         SMALLINT,   -- sacrifice flies
    visiting_hbp        SMALLINT,   -- hit by pitch
    visiting_bb         SMALLINT,
    visiting_ibb        SMALLINT,   -- intentional walks
    visiting_so         SMALLINT,
    visiting_sb         SMALLINT,
    visiting_cs         SMALLINT,
    visiting_gdp        SMALLINT,
    visiting_ci         SMALLINT,   -- catcher interference
    visiting_lob        SMALLINT,

    -- Visiting pitching
    visiting_pitchers   SMALLINT,
    visiting_er         SMALLINT,
    visiting_ter        SMALLINT,   -- team earned runs
    visiting_wp         SMALLINT,
    visiting_balks      SMALLINT,
    visiting_po         SMALLINT,   -- putouts
    visiting_a          SMALLINT,   -- assists
    visiting_e          SMALLINT,
    visiting_pb         SMALLINT,
    visiting_dp         SMALLINT,
    visiting_tp         SMALLINT,

    -- Home team totals
    home_ab             SMALLINT,
    home_h              SMALLINT,
    home_2b             SMALLINT,
    home_3b             SMALLINT,
    home_hr             SMALLINT,
    home_rbi            SMALLINT,
    home_sh             SMALLINT,
    home_sf             SMALLINT,
    home_hbp            SMALLINT,
    home_bb             SMALLINT,
    home_ibb            SMALLINT,
    home_so             SMALLINT,
    home_sb             SMALLINT,
    home_cs             SMALLINT,
    home_gdp            SMALLINT,
    home_ci             SMALLINT,
    home_lob            SMALLINT,

    -- Home pitching
    home_pitchers       SMALLINT,
    home_er             SMALLINT,
    home_ter            SMALLINT,
    home_wp             SMALLINT,
    home_balks          SMALLINT,
    home_po             SMALLINT,
    home_a              SMALLINT,
    home_e              SMALLINT,
    home_pb             SMALLINT,
    home_dp             SMALLINT,
    home_tp             SMALLINT,

    -- Umpires
    ump_home_id         VARCHAR(8),
    ump_home_name       VARCHAR(50),
    ump_1b_id           VARCHAR(8),
    ump_1b_name         VARCHAR(50),
    ump_2b_id           VARCHAR(8),
    ump_2b_name         VARCHAR(50),
    ump_3b_id           VARCHAR(8),
    ump_3b_name         VARCHAR(50),
    ump_lf_id           VARCHAR(8),
    ump_lf_name         VARCHAR(50),
    ump_rf_id           VARCHAR(8),
    ump_rf_name         VARCHAR(50),

    -- Managers
    visiting_mgr_id     VARCHAR(8),
    visiting_mgr_name   VARCHAR(50),
    home_mgr_id         VARCHAR(8),
    home_mgr_name       VARCHAR(50),

    -- Winning/losing/saving pitchers
    winning_pitcher_id  VARCHAR(8),
    winning_pitcher_name VARCHAR(50),
    losing_pitcher_id   VARCHAR(8),
    losing_pitcher_name  VARCHAR(50),
    saving_pitcher_id   VARCHAR(8),
    saving_pitcher_name  VARCHAR(50),

    -- Game-winning RBI
    gwrbi_batter_id     VARCHAR(8),
    gwrbi_batter_name   VARCHAR(50),

    -- Starting batters (visiting, positions 1-9)
    v_start_1_id        VARCHAR(8),   v_start_1_name VARCHAR(50),   v_start_1_pos SMALLINT,
    v_start_2_id        VARCHAR(8),   v_start_2_name VARCHAR(50),   v_start_2_pos SMALLINT,
    v_start_3_id        VARCHAR(8),   v_start_3_name VARCHAR(50),   v_start_3_pos SMALLINT,
    v_start_4_id        VARCHAR(8),   v_start_4_name VARCHAR(50),   v_start_4_pos SMALLINT,
    v_start_5_id        VARCHAR(8),   v_start_5_name VARCHAR(50),   v_start_5_pos SMALLINT,
    v_start_6_id        VARCHAR(8),   v_start_6_name VARCHAR(50),   v_start_6_pos SMALLINT,
    v_start_7_id        VARCHAR(8),   v_start_7_name VARCHAR(50),   v_start_7_pos SMALLINT,
    v_start_8_id        VARCHAR(8),   v_start_8_name VARCHAR(50),   v_start_8_pos SMALLINT,
    v_start_9_id        VARCHAR(8),   v_start_9_name VARCHAR(50),   v_start_9_pos SMALLINT,

    -- Starting batters (home, positions 1-9)
    h_start_1_id        VARCHAR(8),   h_start_1_name VARCHAR(50),   h_start_1_pos SMALLINT,
    h_start_2_id        VARCHAR(8),   h_start_2_name VARCHAR(50),   h_start_2_pos SMALLINT,
    h_start_3_id        VARCHAR(8),   h_start_3_name VARCHAR(50),   h_start_3_pos SMALLINT,
    h_start_4_id        VARCHAR(8),   h_start_4_name VARCHAR(50),   h_start_4_pos SMALLINT,
    h_start_5_id        VARCHAR(8),   h_start_5_name VARCHAR(50),   h_start_5_pos SMALLINT,
    h_start_6_id        VARCHAR(8),   h_start_6_name VARCHAR(50),   h_start_6_pos SMALLINT,
    h_start_7_id        VARCHAR(8),   h_start_7_name VARCHAR(50),   h_start_7_pos SMALLINT,
    h_start_8_id        VARCHAR(8),   h_start_8_name VARCHAR(50),   h_start_8_pos SMALLINT,
    h_start_9_id        VARCHAR(8),   h_start_9_name VARCHAR(50),   h_start_9_pos SMALLINT,

    -- Additional info
    additional_info     TEXT,
    acquisition_info    CHAR(1),                    -- Y=purchased, N=not purchased

    -- Weather
    weather             VARCHAR(50),
    wind_direction      VARCHAR(30),
    wind_speed          SMALLINT,                   -- mph
    temperature         SMALLINT,                   -- degrees F

    -- Source
    source_file         VARCHAR(32),
    raw_line            TEXT,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT now()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_retro_gl_season       ON baseball.retro_game_log (season);
CREATE INDEX IF NOT EXISTS idx_retro_gl_game_date    ON baseball.retro_game_log (game_date);
CREATE INDEX IF NOT EXISTS idx_retro_gl_home_team    ON baseball.retro_game_log (home_team, season);
CREATE INDEX IF NOT EXISTS idx_retro_gl_visiting     ON baseball.retro_game_log (visiting_team, season);
CREATE INDEX IF NOT EXISTS idx_retro_gl_park         ON baseball.retro_game_log (park_id);
