-- 50_tables_core/02_statcast_pitches.sql
-- Statcast pitch-level data from Baseball Savant.
-- One row per pitch; game-level aggregates can be derived from this table.

CREATE TABLE IF NOT EXISTS baseball.statcast_pitches (
    id                  BIGSERIAL       PRIMARY KEY,
    -- Game identifiers
    game_pk             BIGINT          NOT NULL,
    game_date           DATE            NOT NULL,
    season              SMALLINT        NOT NULL,
    game_type           VARCHAR(2),
    -- At-bat / pitch identifiers
    at_bat_number       SMALLINT,
    pitch_number        SMALLINT,
    inning              SMALLINT,
    inning_topbot       VARCHAR(3),                        -- 'Top' | 'Bot'
    -- Pitcher
    pitcher_id          INTEGER         NOT NULL,
    pitcher_name        VARCHAR(64),
    p_throws            CHAR(1),                           -- 'L' | 'R'
    -- Batter
    batter_id           INTEGER         NOT NULL,
    batter_name         VARCHAR(64),
    stand               CHAR(1),                           -- 'L' | 'R'
    -- Pitch classification
    pitch_type          VARCHAR(4),
    pitch_name          VARCHAR(32),
    -- Pitch metrics
    release_speed       NUMERIC(5,1),
    release_spin_rate   INTEGER,
    release_extension   NUMERIC(4,2),
    pfx_x               NUMERIC(6,3),
    pfx_z               NUMERIC(6,3),
    plate_x             NUMERIC(6,3),
    plate_z             NUMERIC(6,3),
    sz_top              NUMERIC(4,2),
    sz_bot              NUMERIC(4,2),
    -- Hit data
    launch_speed        NUMERIC(5,1),
    launch_angle        NUMERIC(5,1),
    hit_distance_sc     NUMERIC(6,1),
    hc_x                NUMERIC(7,2),
    hc_y                NUMERIC(7,2),
    hit_location        SMALLINT,
    -- Outcome
    description         VARCHAR(64),
    events              VARCHAR(64),
    type                VARCHAR(1),                        -- 'S' | 'B' | 'X'
    bb_type             VARCHAR(32),
    -- Count
    balls               SMALLINT,
    strikes             SMALLINT,
    outs_when_up        SMALLINT,
    -- On-base
    on_1b               INTEGER,
    on_2b               INTEGER,
    on_3b               INTEGER,
    -- Expected stats
    estimated_ba_using_speedangle   NUMERIC(5,3),
    estimated_woba_using_speedangle NUMERIC(5,3),
    woba_value          NUMERIC(5,3),
    woba_denom          SMALLINT,
    babip_value         NUMERIC(5,3),
    iso_value           NUMERIC(5,3),
    -- Metadata
    home_team           VARCHAR(4),
    away_team           VARCHAR(4),
    raw_json            JSONB,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT now(),
    -- Unique constraint: one row per game/at-bat/pitch
    CONSTRAINT uq_statcast_pitch UNIQUE (game_pk, at_bat_number, pitch_number)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_statcast_season
    ON baseball.statcast_pitches (season);

CREATE INDEX IF NOT EXISTS idx_statcast_game_pk
    ON baseball.statcast_pitches (game_pk);

CREATE INDEX IF NOT EXISTS idx_statcast_pitcher
    ON baseball.statcast_pitches (pitcher_id, season);

CREATE INDEX IF NOT EXISTS idx_statcast_batter
    ON baseball.statcast_pitches (batter_id, season);

CREATE INDEX IF NOT EXISTS idx_statcast_game_date
    ON baseball.statcast_pitches (game_date);
