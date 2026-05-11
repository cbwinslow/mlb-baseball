-- ============================================================
-- 03_retro_events.sql
-- Retrosheet play-by-play event data.
-- One row per play/event from Retrosheet event files (.EVA / .EVN).
-- Column names follow the Retrosheet event file field specification.
-- Schema: baseball
-- Mirrors: baseball.sources.retrosheet.ingestor (RetroEventFileIngestor)
-- ============================================================

CREATE TABLE IF NOT EXISTS baseball.retro_events (
    id                  BIGSERIAL       PRIMARY KEY,

    -- Game identification
    game_id             VARCHAR(12)     NOT NULL,   -- e.g. NYA202304060
    season              SMALLINT        NOT NULL,
    game_date           DATE            NOT NULL,
    home_team           VARCHAR(3)      NOT NULL,
    visiting_team       VARCHAR(3)      NOT NULL,

    -- Event sequence
    event_id            SMALLINT        NOT NULL,   -- sequential within game
    inning              SMALLINT        NOT NULL,
    batting_team        CHAR(1)         NOT NULL,   -- '0'=visiting '1'=home
    outs                SMALLINT        NOT NULL,

    -- Batter / pitcher
    batter_id           VARCHAR(8)      NOT NULL,   -- Retrosheet player ID
    pitcher_id          VARCHAR(8)      NOT NULL,
    batter_hand         CHAR(1),
    pitcher_hand        CHAR(1),

    -- Count
    balls               SMALLINT,
    strikes             SMALLINT,

    -- Base state before play
    runner_on_1b        VARCHAR(8),
    runner_on_2b        VARCHAR(8),
    runner_on_3b        VARCHAR(8),

    -- Play description
    play_text           VARCHAR(64)     NOT NULL,   -- raw event string
    event_type          SMALLINT,                   -- numeric Retrosheet event code
    event_cd            SMALLINT,                   -- 0=out,1=single,2=double,etc.
    hit_val             SMALLINT,                   -- 0=no hit,1=S,2=D,3=T,4=HR

    -- Batted ball
    batted_ball_type    VARCHAR(4),                 -- G=ground,L=line,F=fly,P=popup
    hit_location        SMALLINT,                   -- fielder position code (1-9)

    -- RBI / runs
    rbi_ct              SMALLINT        NOT NULL DEFAULT 0,
    runs_scored         SMALLINT        NOT NULL DEFAULT 0,

    -- Fielding
    fielded_by          SMALLINT,

    -- Extra flags
    sh_fl               BOOLEAN         NOT NULL DEFAULT FALSE,  -- sacrifice hit
    sf_fl               BOOLEAN         NOT NULL DEFAULT FALSE,  -- sacrifice fly
    dp_fl               BOOLEAN         NOT NULL DEFAULT FALSE,  -- double play
    tp_fl               BOOLEAN         NOT NULL DEFAULT FALSE,  -- triple play
    wp_fl               BOOLEAN         NOT NULL DEFAULT FALSE,  -- wild pitch
    pb_fl               BOOLEAN         NOT NULL DEFAULT FALSE,  -- passed ball

    -- Source
    source_file         VARCHAR(32),
    raw_line            TEXT,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT now(),

    CONSTRAINT uq_retro_event UNIQUE (game_id, event_id)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_retro_season
    ON baseball.retro_events (season);

CREATE INDEX IF NOT EXISTS idx_retro_game_id
    ON baseball.retro_events (game_id);

CREATE INDEX IF NOT EXISTS idx_retro_batter
    ON baseball.retro_events (batter_id, season);

CREATE INDEX IF NOT EXISTS idx_retro_pitcher
    ON baseball.retro_events (pitcher_id, season);

CREATE INDEX IF NOT EXISTS idx_retro_game_date
    ON baseball.retro_events (game_date);

CREATE INDEX IF NOT EXISTS idx_retro_event_type
    ON baseball.retro_events (event_type);

CREATE INDEX IF NOT EXISTS idx_retro_teams
    ON baseball.retro_events (home_team, visiting_team, season);
