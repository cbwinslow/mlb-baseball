-- ============================================================
-- 08_schedule.sql
-- Game schedule table (future + past)
-- Schema: baseball
-- Mirrors: baseball.db.models.Schedule
-- ============================================================

CREATE TABLE IF NOT EXISTS baseball.schedule (
    schedule_id         SERIAL          PRIMARY KEY,
    game_id             INTEGER         UNIQUE REFERENCES baseball.game(game_id),
    game_datetime_utc   TIMESTAMP       NOT NULL,
    game_date           DATE            NOT NULL,
    season              INTEGER         NOT NULL,
    home_team_id        INTEGER         NOT NULL REFERENCES baseball.team(team_id),
    away_team_id        INTEGER         NOT NULL REFERENCES baseball.team(team_id),
    park_id             INTEGER         REFERENCES baseball.park(park_id),
    game_status         VARCHAR(20),                -- Scheduled, Completed, Postponed
    created_at          TIMESTAMP       NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMP       NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS ix_schedule_datetime    ON baseball.schedule (game_datetime_utc);
CREATE INDEX IF NOT EXISTS ix_schedule_date        ON baseball.schedule (game_date);
CREATE INDEX IF NOT EXISTS ix_schedule_season      ON baseball.schedule (season);
CREATE INDEX IF NOT EXISTS ix_schedule_season_date ON baseball.schedule (season, game_date);
CREATE INDEX IF NOT EXISTS ix_schedule_home_team   ON baseball.schedule (home_team_id);
CREATE INDEX IF NOT EXISTS ix_schedule_away_team   ON baseball.schedule (away_team_id);
