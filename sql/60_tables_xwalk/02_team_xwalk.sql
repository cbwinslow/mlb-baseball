-- ============================================================
-- 02_team_xwalk.sql
-- Team ID crosswalk across all data sources
-- Schema: baseball
-- Mirrors: baseball.db.models.TeamXwalk
-- ============================================================

CREATE TABLE IF NOT EXISTS baseball.team_xwalk (
    xwalk_id            SERIAL          PRIMARY KEY,
    team_id             INTEGER         NOT NULL REFERENCES baseball.team(team_id),
    mlbam_id            INTEGER         UNIQUE,
    retrosheet_id       VARCHAR(5)      UNIQUE,
    lahman_id           VARCHAR(5)      UNIQUE,
    bbref_id            VARCHAR(20)     UNIQUE,
    created_at          TIMESTAMP       NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMP       NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS ix_team_xwalk_team_id     ON baseball.team_xwalk (team_id);
CREATE INDEX IF NOT EXISTS ix_team_xwalk_mlbam       ON baseball.team_xwalk (mlbam_id);
CREATE INDEX IF NOT EXISTS ix_team_xwalk_retrosheet  ON baseball.team_xwalk (retrosheet_id);
CREATE INDEX IF NOT EXISTS ix_team_xwalk_bbref       ON baseball.team_xwalk (bbref_id);
