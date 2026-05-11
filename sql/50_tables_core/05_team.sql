-- ============================================================
-- 05_team.sql
-- Core team dimension table
-- Schema: baseball
-- Mirrors: baseball.db.models.Team
-- ============================================================

CREATE TABLE IF NOT EXISTS baseball.team (
    team_id             SERIAL          PRIMARY KEY,
    team_mlbam_id       INTEGER         UNIQUE,
    team_retrosheet_id  VARCHAR(5)      UNIQUE,
    team_lahman_id      VARCHAR(5)      UNIQUE,
    franchise_id        VARCHAR(20),
    team_name           VARCHAR(50)     NOT NULL UNIQUE,
    team_abbr           VARCHAR(3)      NOT NULL UNIQUE,
    league              VARCHAR(2)      NOT NULL,   -- AL, NL
    division            VARCHAR(10),
    location            VARCHAR(100),
    founded_year        INTEGER,
    created_at          TIMESTAMP       NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMP       NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS ix_team_league_division ON baseball.team (league, division);
CREATE INDEX IF NOT EXISTS ix_team_mlbam           ON baseball.team (team_mlbam_id);
CREATE INDEX IF NOT EXISTS ix_team_retro           ON baseball.team (team_retrosheet_id);
CREATE INDEX IF NOT EXISTS ix_team_abbr            ON baseball.team (team_abbr);
