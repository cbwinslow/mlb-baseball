-- =============================================================================
-- Raw Statcast Pitches Table
-- Source: Baseball Savant (baseballsavant.mlb.com)
-- Docs:   https://baseballsavant.mlb.com/csv-docs
-- Via:    pybaseball statcast(), statcast_pitcher(), statcast_batter()
-- Notes:  Every field from the Statcast CSV export is captured here as-is.
--         Deprecated fields are retained for historical data compatibility.
--         plate_x / plate_z semantics changed in 2026 (front-of-plate -> middle-of-plate).
-- =============================================================================

CREATE TABLE IF NOT EXISTS raw.statcast_pitches (
    -- -------------------------------------------------------------------------
    -- Pitch identification
    -- -------------------------------------------------------------------------
    pitch_type                              TEXT,           -- Type of pitch derived from Statcast
    game_date                               DATE,           -- Date of the Game
    game_year                               SMALLINT,       -- Year game took place
    game_pk                                 BIGINT,         -- Unique Id for Game
    game_type                               TEXT,           -- E=Exhibition, S=Spring, R=Regular, F=WC, D=ALDS, L=LCS, W=WS
    sv_id                                   TEXT,           -- Non-unique Id of play event per game
    at_bat_number                           SMALLINT,       -- Plate appearance number of the game
    pitch_number                            SMALLINT,       -- Total pitch number of the plate appearance
    pitch_name                              TEXT,           -- Name of pitch from Statcast

    -- -------------------------------------------------------------------------
    -- Players
    -- -------------------------------------------------------------------------
    player_name                             TEXT,           -- Player name tied to the event
    batter                                  INTEGER,        -- MLB Player Id for batter
    pitcher                                 INTEGER,        -- MLB Player Id for pitcher (event column)
    stand                                   CHAR(1),        -- Side of plate batter is standing (L/R)
    p_throws                                CHAR(1),        -- Hand pitcher throws with (L/R)
    home_team                               TEXT,           -- Abbreviation of home team
    away_team                               TEXT,           -- Abbreviation of away team

    -- -------------------------------------------------------------------------
    -- Fielders (pre-pitch)
    -- -------------------------------------------------------------------------
    fielder_2                               INTEGER,        -- MLB Player Id for Catcher
    fielder_3                               INTEGER,        -- MLB Player Id for 1B
    fielder_4                               INTEGER,        -- MLB Player Id for 2B
    fielder_5                               INTEGER,        -- MLB Player Id for 3B
    fielder_6                               INTEGER,        -- MLB Player Id for SS
    fielder_7                               INTEGER,        -- MLB Player Id for LF
    fielder_8                               INTEGER,        -- MLB Player Id for CF
    fielder_9                               INTEGER,        -- MLB Player Id for RF

    -- -------------------------------------------------------------------------
    -- Game situation (pre-pitch)
    -- -------------------------------------------------------------------------
    on_3b                                   INTEGER,        -- MLB Player Id of Runner on 3B
    on_2b                                   INTEGER,        -- MLB Player Id of Runner on 2B
    on_1b                                   INTEGER,        -- MLB Player Id of Runner on 1B
    outs_when_up                            SMALLINT,       -- Number of outs pre-pitch
    inning                                  SMALLINT,       -- Inning number pre-pitch
    inning_topbot                           TEXT,           -- Top or Bottom of inning
    balls                                   SMALLINT,       -- Pre-pitch balls in count
    strikes                                 SMALLINT,       -- Pre-pitch strikes in count

    -- -------------------------------------------------------------------------
    -- Pitch result
    -- -------------------------------------------------------------------------
    events                                  TEXT,           -- Event of the resulting Plate Appearance
    description                             TEXT,           -- Description of the resulting pitch
    des                                     TEXT,           -- Plate appearance description from game day
    type                                    CHAR(1),        -- B=ball, S=strike, X=in play
    zone                                    SMALLINT,       -- Zone location of ball when crossing plate
    hit_location                            SMALLINT,       -- Position of first fielder to touch the ball
    bb_type                                 TEXT,           -- Batted ball type: ground_ball, line_drive, fly_ball, popup

    -- -------------------------------------------------------------------------
    -- Pitch physics: release
    -- -------------------------------------------------------------------------
    release_speed                           NUMERIC(6,2),   -- Pitch velocity in MPH (out-of-hand)
    release_pos_x                           NUMERIC(8,4),   -- Horizontal release position (ft, catcher perspective)
    release_pos_z                           NUMERIC(8,4),   -- Vertical release position (ft, catcher perspective)
    release_pos_y                           NUMERIC(8,4),   -- Release position depth (ft from catcher)
    release_spin                            NUMERIC(8,2),   -- Spin rate (RPM) tracked by Statcast
    release_extension                       NUMERIC(6,3),   -- Release extension in feet
    effective_speed                         NUMERIC(6,2),   -- Derived speed based on extension
    arm_angle                               NUMERIC(7,3),   -- Angle of pitcher's throwing arm at release

    -- -------------------------------------------------------------------------
    -- Pitch physics: trajectory (at y=50 ft)
    -- -------------------------------------------------------------------------
    vx0                                     NUMERIC(10,5),  -- Velocity in x-dimension at y=50 (ft/s)
    vy0                                     NUMERIC(10,5),  -- Velocity in y-dimension at y=50 (ft/s)
    vz0                                     NUMERIC(10,5),  -- Velocity in z-dimension at y=50 (ft/s)
    ax                                      NUMERIC(10,5),  -- Acceleration in x-dimension (ft/s²)
    ay                                      NUMERIC(10,5),  -- Acceleration in y-dimension (ft/s²)
    az                                      NUMERIC(10,5),  -- Acceleration in z-dimension (ft/s²)
    pfx_x                                   NUMERIC(8,4),   -- Horizontal movement in feet (catcher perspective)
    pfx_z                                   NUMERIC(8,4),   -- Vertical movement in feet (catcher perspective)
    spin_axis                               SMALLINT,       -- Spin axis 0-360 degrees

    -- -------------------------------------------------------------------------
    -- Pitch location at plate
    -- -------------------------------------------------------------------------
    plate_x                                 NUMERIC(8,4),   -- Horizontal position at plate (ft, catcher perspective)
    plate_z                                 NUMERIC(8,4),   -- Vertical position at plate (ft, catcher perspective)
    sz_top                                  NUMERIC(6,3),   -- Top of strike zone (ft)
    sz_bot                                  NUMERIC(6,3),   -- Bottom of strike zone (ft)

    -- -------------------------------------------------------------------------
    -- Hit metrics
    -- -------------------------------------------------------------------------
    hc_x                                    NUMERIC(8,3),   -- Hit coordinate X of batted ball
    hc_y                                    NUMERIC(8,3),   -- Hit coordinate Y of batted ball
    hit_distance                            SMALLINT,       -- Projected hit distance in feet
    launch_speed                            NUMERIC(6,2),   -- Exit velocity (MPH)
    launch_angle                            NUMERIC(6,2),   -- Launch angle (degrees)
    launch_speed_angle                      SMALLINT,       -- Speed/angle zone 1-6 (Weak/Topped/Under/Flare/Solid/Barrel)
    hyper_speed                             NUMERIC(6,2),   -- Adjusted EV (floor of 88 mph)

    -- -------------------------------------------------------------------------
    -- Expected value metrics
    -- -------------------------------------------------------------------------
    estimated_ba_using_speedangle           NUMERIC(6,4),   -- xBA based on launch angle and EV
    estimated_woba_using_speedangle         NUMERIC(6,4),   -- xwOBA based on launch angle and EV
    woba_value                              NUMERIC(6,4),   -- wOBA value based on result
    woba_denom                              SMALLINT,       -- wOBA denominator
    babip_value                             SMALLINT,       -- BABIP value
    iso_value                               NUMERIC(6,4),   -- ISO value

    -- -------------------------------------------------------------------------
    -- Score and win expectancy
    -- -------------------------------------------------------------------------
    home_score                              SMALLINT,       -- Pre-pitch home score
    away_score                              SMALLINT,       -- Pre-pitch away score
    bat_score                               SMALLINT,       -- Pre-pitch batting team score
    fld_score                               SMALLINT,       -- Pre-pitch fielding team score
    post_home_score                         SMALLINT,       -- Post-pitch home score
    post_away_score                         SMALLINT,       -- Post-pitch away score
    post_bat_score                          SMALLINT,       -- Post-pitch batting team score
    home_score_diff                         SMALLINT,       -- Home minus Away score
    bat_score_diff                          SMALLINT,       -- Batting minus Pitching team score
    home_win_exp                            NUMERIC(8,5),   -- Home team win expectancy
    bat_win_exp                             NUMERIC(8,5),   -- Batting team win expectancy
    delta_home_win_exp                      NUMERIC(8,5),   -- Change in home win expectancy
    delta_run_exp                           NUMERIC(8,5),   -- Change in run expectancy

    -- -------------------------------------------------------------------------
    -- Fielding alignment
    -- -------------------------------------------------------------------------
    if_fielding_alignment                   TEXT,           -- Infield alignment at time of pitch
    of_fielding_alignment                   TEXT,           -- Outfield alignment at time of pitch

    -- -------------------------------------------------------------------------
    -- Player age
    -- -------------------------------------------------------------------------
    age_pit                                 NUMERIC(5,1),   -- Pitcher age on 12/31
    age_bat                                 NUMERIC(5,1),   -- Batter age on 12/31
    age_pit_legacy                          NUMERIC(5,1),   -- Pitcher age on 6/30 (legacy)
    age_bat_legacy                          NUMERIC(5,1),   -- Batter age on 6/30 (legacy)

    -- -------------------------------------------------------------------------
    -- Times through order / game context
    -- -------------------------------------------------------------------------
    n_thruorder_pitcher                     SMALLINT,       -- Pitcher times through the order
    n_priorpa_thisgame_player_at_bat        SMALLINT,       -- Prior PAs this game for batter
    pitcher_days_since_prev_game            SMALLINT,       -- Days since pitcher's last game
    batter_days_since_prev_game             SMALLINT,       -- Days since batter's last game
    pitcher_days_until_next_game            SMALLINT,       -- Days until pitcher's next game
    batter_days_until_next_game             SMALLINT,       -- Days until batter's next game

    -- -------------------------------------------------------------------------
    -- Break metrics (new API fields)
    -- -------------------------------------------------------------------------
    api_break_z_with_gravity                NUMERIC(8,3),   -- Vertical break with gravity
    api_break_x_arm                         NUMERIC(8,3),   -- Break toward pitcher's arm side (in)
    api_break_x_batter_in                   NUMERIC(8,3),   -- Break toward batter's side of plate (in)

    -- -------------------------------------------------------------------------
    -- Bat tracking metrics (2023+)
    -- -------------------------------------------------------------------------
    attack_angle                            NUMERIC(7,3),   -- Vertical angle of bat sweet-spot at impact
    attack_direction                        NUMERIC(7,3),   -- Horizontal angle of bat sweet-spot at impact
    swing_path_tilt                         NUMERIC(7,3),   -- Vertical tilt of swing plane
    intercept_ball_minus_batter_pos_x_inches NUMERIC(8,3),  -- Horizontal distance bat/ball intercept vs batter CoM
    intercept_ball_minus_batter_pos_y_inches NUMERIC(8,3),  -- Y distance bat/ball intercept vs batter CoM

    -- -------------------------------------------------------------------------
    -- Deprecated fields (retained for historical data compatibility)
    -- -------------------------------------------------------------------------
    spin_dir                                NUMERIC(8,3),   -- DEPRECATED: old tracking system
    spin_rate_deprecated                    NUMERIC(8,2),   -- DEPRECATED: replaced by release_spin
    break_angle_deprecated                  NUMERIC(8,3),   -- DEPRECATED
    break_length_deprecated                 NUMERIC(8,3),   -- DEPRECATED
    tfs_deprecated                          BIGINT,         -- DEPRECATED: old tracking system
    tfs_zulu_deprecated                     BIGINT,         -- DEPRECATED: old tracking system
    umpire                                  TEXT,           -- DEPRECATED: old tracking system

    -- -------------------------------------------------------------------------
    -- Audit columns
    -- -------------------------------------------------------------------------
    _ingested_at                            TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_file                            TEXT
);

COMMENT ON TABLE raw.statcast_pitches IS
    'Raw Statcast pitch-level data ingested as-is from Baseball Savant. '
    'Source: https://baseballsavant.mlb.com/csv-docs. '
    'Covers 2008-present. plate_x/plate_z semantics changed in 2026 (front->middle of plate).';
