-- 50_tables_core/01_mlb_schedule.sql
-- MLB schedule / game calendar table.
-- Stores one row per scheduled game as returned by the MLB StatsAPI.

CREATE TABLE IF NOT EXISTS baseball.mlb_schedule (
    id                  BIGSERIAL       PRIMARY KEY,
    game_pk             BIGINT          NOT NULL,
    season              SMALLINT        NOT NULL,
    game_date           DATE            NOT NULL,
    game_type           VARCHAR(2)      NOT NULL,          -- R=Regular, P=Postseason, S=Spring
    status              VARCHAR(32)     NOT NULL DEFAULT 'scheduled',
    home_team_id        INTEGER         NOT NULL,
    home_team_name      VARCHAR(64),
    away_team_id        INTEGER         NOT NULL,
    away_team_name      VARCHAR(64),
    venue_id            INTEGER,
    venue_name          VARCHAR(128),
    home_score          SMALLINT,
    away_score          SMALLINT,
    inning              SMALLINT,
    double_header       CHAR(1)         NOT NULL DEFAULT 'N',
    day_night           VARCHAR(5),                        -- 'day' | 'night'
    series_description  VARCHAR(64),
    series_game_number  SMALLINT,
    games_in_series     SMALLINT,
    raw_json            JSONB,                             -- full API response for re-processing
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT now(),
    CONSTRAINT uq_mlb_schedule_game_pk UNIQUE (game_pk)
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_mlb_schedule_season
    ON baseball.mlb_schedule (season);

CREATE INDEX IF NOT EXISTS idx_mlb_schedule_game_date
    ON baseball.mlb_schedule (game_date);

CREATE INDEX IF NOT EXISTS idx_mlb_schedule_teams
    ON baseball.mlb_schedule (home_team_id, away_team_id);

-- Auto-update updated_at on row change
CREATE OR REPLACE FUNCTION baseball.set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END
$$;

DROP TRIGGER IF EXISTS trg_mlb_schedule_updated_at ON baseball.mlb_schedule;
CREATE TRIGGER trg_mlb_schedule_updated_at
    BEFORE UPDATE ON baseball.mlb_schedule
    FOR EACH ROW EXECUTE FUNCTION baseball.set_updated_at();
