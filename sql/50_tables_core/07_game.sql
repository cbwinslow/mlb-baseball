-- ============================================================
-- 07_game.sql
-- Core game fact table
-- Schema: baseball
-- Mirrors: baseball.db.models.Game
-- ============================================================

CREATE TABLE IF NOT EXISTS baseball.game (
    game_id             SERIAL          PRIMARY KEY,
    game_mlbam_id       VARCHAR(50)     UNIQUE,
    game_retrosheet_id  VARCHAR(50)     UNIQUE,
    game_datetime_utc   TIMESTAMP       NOT NULL,
    game_date           DATE            NOT NULL,
    season              INTEGER         NOT NULL,
    game_number         INTEGER,                    -- 1 = first game, 2 = doubleheader
    game_type           VARCHAR(10),                -- S, P, etc.
    home_team_id        INTEGER         NOT NULL REFERENCES baseball.team(team_id),
    away_team_id        INTEGER         NOT NULL REFERENCES baseball.team(team_id),
    park_id             INTEGER         REFERENCES baseball.park(park_id),
    home_score          INTEGER,
    away_score          INTEGER,
    game_status         VARCHAR(20),                -- Final, Ongoing, Postponed
    innings_played      INTEGER,
    duration_minutes    INTEGER,
    attendance          INTEGER,
    weather_condition   VARCHAR(50),
    weather_temp_f      INTEGER,
    weather_wind_mph    NUMERIC(5,1),
    created_at          TIMESTAMP       NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMP       NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS ix_game_datetime       ON baseball.game (game_datetime_utc);
CREATE INDEX IF NOT EXISTS ix_game_date           ON baseball.game (game_date);
CREATE INDEX IF NOT EXISTS ix_game_season         ON baseball.game (season);
CREATE INDEX IF NOT EXISTS ix_game_season_date    ON baseball.game (season, game_date);
CREATE INDEX IF NOT EXISTS ix_game_teams          ON baseball.game (home_team_id, away_team_id);
CREATE INDEX IF NOT EXISTS ix_game_mlbam          ON baseball.game (game_mlbam_id);
CREATE INDEX IF NOT EXISTS ix_game_retro          ON baseball.game (game_retrosheet_id);
