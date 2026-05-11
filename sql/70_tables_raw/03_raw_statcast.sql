-- =============================================================
-- 03_raw_statcast.sql
-- RAW Statcast / Baseball Savant pitch-level data
-- Source: https://baseballsavant.mlb.com/csv-docs
--         pybaseball statcast() function
-- Schema: raw
-- Table:  raw.statcast_pitches
-- NOTE:   Every column from the official Baseball Savant CSV export
--         is preserved here.  Build your models on top of this table.
-- =============================================================

CREATE TABLE IF NOT EXISTS raw.statcast_pitches (

    -- -------------------------------------------------------
    -- Pitch identification
    -- -------------------------------------------------------
    pitch_type                    TEXT,         -- pitch type code (FF, SL, CU, etc.)
    game_date                     DATE,
    release_speed                 NUMERIC(6,2), -- velocity in MPH out-of-hand
    release_pos_x                 NUMERIC(7,4), -- horiz release position (catcher POV)
    release_pos_z                 NUMERIC(7,4), -- vert release position
    player_name                   TEXT,
    batter                        BIGINT,       -- MLBAM batter ID
    pitcher                       BIGINT,       -- MLBAM pitcher ID
    events                        TEXT,         -- plate appearance result
    description                   TEXT,         -- pitch result description

    -- -------------------------------------------------------
    -- Deprecated PitchFX columns (retained for history)
    -- -------------------------------------------------------
    spin_dir                      NUMERIC(8,4),
    spin_rate_deprecated          NUMERIC(8,4),
    break_angle_deprecated        NUMERIC(7,4),
    break_length_deprecated       NUMERIC(7,4),
    tfs_deprecated                TEXT,
    tfs_zulu_deprecated           TEXT,
    umpire                        TEXT,

    -- -------------------------------------------------------
    -- Game & situational
    -- -------------------------------------------------------
    zone                          INTEGER,      -- strike zone location 1-14
    des                           TEXT,         -- play description
    game_type                     TEXT,         -- E/S/R/F/D/L/W
    stand                         TEXT,         -- batter handedness L/R
    p_throws                      TEXT,         -- pitcher handedness L/R
    home_team                     TEXT,
    away_team                     TEXT,
    type                          TEXT,         -- B=ball, S=strike, X=in play
    hit_location                  INTEGER,
    bb_type                       TEXT,         -- ground_ball / line_drive / fly_ball / popup
    balls                         SMALLINT,
    strikes                       SMALLINT,
    game_year                     SMALLINT,
    on_3b                         BIGINT,       -- runner on 3B MLBAM ID
    on_2b                         BIGINT,
    on_1b                         BIGINT,
    outs_when_up                  SMALLINT,
    inning                        SMALLINT,
    inning_topbot                 TEXT,         -- Top / Bot
    game_pk                       BIGINT,       -- MLB game primary key
    at_bat_number                 INTEGER,
    pitch_number                  SMALLINT,     -- pitch # in plate appearance
    home_score                    SMALLINT,
    away_score                    SMALLINT,
    bat_score                     SMALLINT,
    fld_score                     SMALLINT,
    post_home_score               SMALLINT,
    post_away_score               SMALLINT,
    post_bat_score                SMALLINT,
    if_fielding_alignment         TEXT,
    of_fielding_alignment         TEXT,

    -- -------------------------------------------------------
    -- Movement & trajectory
    -- -------------------------------------------------------
    pfx_x                         NUMERIC(7,4), -- horiz break (inches)
    pfx_z                         NUMERIC(7,4), -- vert break (inches)
    plate_x                       NUMERIC(7,4), -- horiz position at plate
    plate_z                       NUMERIC(7,4), -- vert position at plate
    hc_x                          NUMERIC(8,4), -- hit coordinate X
    hc_y                          NUMERIC(8,4), -- hit coordinate Y
    vx0                           NUMERIC(9,4),
    vy0                           NUMERIC(9,4),
    vz0                           NUMERIC(9,4),
    ax                            NUMERIC(9,4),
    ay                            NUMERIC(9,4),
    az                            NUMERIC(9,4),
    sz_top                        NUMERIC(6,3), -- top of strike zone (ft)
    sz_bot                        NUMERIC(6,3), -- bottom of strike zone (ft)
    release_pos_y                 NUMERIC(7,4),
    effective_speed               NUMERIC(6,2),
    release_spin_rate             NUMERIC(8,2),
    release_extension             NUMERIC(6,3), -- extension in feet
    spin_axis                     NUMERIC(7,2),
    api_break_z_with_gravity      NUMERIC(7,4),
    api_break_x_arm               NUMERIC(7,4),
    api_break_x_batter_in         NUMERIC(7,4),

    -- -------------------------------------------------------
    -- Batted ball
    -- -------------------------------------------------------
    hit_distance_sc               NUMERIC(7,2),
    launch_speed                  NUMERIC(6,2), -- exit velocity (mph)
    launch_angle                  NUMERIC(6,2), -- degrees
    estimated_ba_using_speedangle NUMERIC(6,4),
    estimated_woba_using_speedangle NUMERIC(6,4),
    woba_value                    NUMERIC(6,4),
    woba_denom                    SMALLINT,
    babip_value                   SMALLINT,
    iso_value                     SMALLINT,
    launch_speed_angle            SMALLINT,     -- 1-6 barrel zone code

    -- -------------------------------------------------------
    -- Fielder IDs (MLBAM)
    -- -------------------------------------------------------
    fielder_2                     BIGINT,       -- catcher
    fielder_3                     BIGINT,       -- 1B
    fielder_4                     BIGINT,       -- 2B
    fielder_5                     BIGINT,       -- 3B
    fielder_6                     BIGINT,       -- SS
    fielder_7                     BIGINT,       -- LF
    fielder_8                     BIGINT,       -- CF
    fielder_9                     BIGINT,       -- RF

    -- -------------------------------------------------------
    -- Advanced / newer columns
    -- -------------------------------------------------------
    sv_id                         TEXT,         -- unique pitch ID (legacy)
    pitch_name                    TEXT,
    age_pit_legacy                SMALLINT,
    age_bat_legacy                SMALLINT,
    age_pit                       NUMERIC(5,2),
    age_bat                       NUMERIC(5,2),
    n_thruorder_pitcher           SMALLINT,
    n_priorpa_thisgame_player_at_bat SMALLINT,
    pitcher_days_since_prev_game  SMALLINT,
    batter_days_since_prev_game   SMALLINT,
    pitcher_days_until_next_game  SMALLINT,
    batter_days_until_next_game   SMALLINT,
    arm_angle                     NUMERIC(6,2),
    attack_angle                  NUMERIC(6,2),
    attack_direction              NUMERIC(6,2),
    swing_path_tilt               NUMERIC(6,2),
    intercept_ball_minus_batter_pos_x_inches NUMERIC(7,3),
    intercept_ball_minus_batter_pos_y_inches NUMERIC(7,3),
    delta_home_win_exp            NUMERIC(8,5),
    delta_run_exp                 NUMERIC(8,5),
    hyper_speed                   NUMERIC(6,2),
    home_score_diff               SMALLINT,
    bat_score_diff                SMALLINT,
    home_win_exp                  NUMERIC(8,5),
    bat_win_exp                   NUMERIC(8,5),

    -- -------------------------------------------------------
    -- Ingestion metadata
    -- -------------------------------------------------------
    source_file                   TEXT,
    loaded_at                     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Indexes
CREATE INDEX IF NOT EXISTS ix_statcast_game_date   ON raw.statcast_pitches (game_date);
CREATE INDEX IF NOT EXISTS ix_statcast_game_pk     ON raw.statcast_pitches (game_pk);
CREATE INDEX IF NOT EXISTS ix_statcast_batter      ON raw.statcast_pitches (batter);
CREATE INDEX IF NOT EXISTS ix_statcast_pitcher     ON raw.statcast_pitches (pitcher);
CREATE INDEX IF NOT EXISTS ix_statcast_game_year   ON raw.statcast_pitches (game_year);
CREATE INDEX IF NOT EXISTS ix_statcast_home_team   ON raw.statcast_pitches (home_team, game_year);
CREATE INDEX IF NOT EXISTS ix_statcast_away_team   ON raw.statcast_pitches (away_team, game_year);
