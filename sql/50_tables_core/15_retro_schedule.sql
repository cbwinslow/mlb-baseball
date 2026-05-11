-- =============================================================
-- 15_retro_schedule.sql
-- Retrosheet published schedule (pre-season schedule data)
-- Schema: baseball
-- Table:  retro_schedule
-- =============================================================

CREATE TABLE IF NOT EXISTS baseball.retro_schedule (

    -- Primary key
    schedule_id       BIGSERIAL PRIMARY KEY,

    -- Game identification
    game_date         DATE          NOT NULL,
    game_number       SMALLINT      NOT NULL DEFAULT 0,  -- 0=single, 1=first of DH, 2=second
    day_of_week       VARCHAR(3),                        -- Mon, Tue, Wed...

    -- Teams
    visiting_team     VARCHAR(3)    NOT NULL,
    visiting_league   CHAR(2),
    visiting_game_num SMALLINT,
    home_team         VARCHAR(3)    NOT NULL,
    home_league       CHAR(2),
    home_game_num     SMALLINT,

    -- Game info
    time_of_day       CHAR(1),                 -- D=day, N=night, B=both (twilight)
    postponement_flag CHAR(1),                 -- blank or postponement/cancellation indicator
    makeup_date       DATE,                    -- date makeup is scheduled if postponed

    -- Season
    season            SMALLINT      NOT NULL,

    -- Source metadata
    source_file       VARCHAR(64),
    created_at        TIMESTAMPTZ   NOT NULL DEFAULT now()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_retro_sched_season
    ON baseball.retro_schedule (season);
CREATE INDEX IF NOT EXISTS idx_retro_sched_game_date
    ON baseball.retro_schedule (game_date);
CREATE INDEX IF NOT EXISTS idx_retro_sched_home_team
    ON baseball.retro_schedule (home_team, season);
CREATE INDEX IF NOT EXISTS idx_retro_sched_visiting_team
    ON baseball.retro_schedule (visiting_team, season);
CREATE UNIQUE INDEX IF NOT EXISTS uidx_retro_sched_game
    ON baseball.retro_schedule (game_date, home_team, game_number);
