-- ============================================================
-- 06_park.sql
-- Core park/stadium dimension table
-- Schema: baseball
-- Mirrors: baseball.db.models.Park
-- ============================================================

CREATE TABLE IF NOT EXISTS baseball.park (
    park_id             SERIAL          PRIMARY KEY,
    park_mlbam_id       INTEGER         UNIQUE,
    park_retrosheet_id  VARCHAR(10)     UNIQUE,
    park_name           VARCHAR(100)    NOT NULL UNIQUE,
    park_alias          VARCHAR(100),
    city                VARCHAR(50),
    state               VARCHAR(2),
    country             VARCHAR(50)     DEFAULT 'USA',
    home_team_id        INTEGER         REFERENCES baseball.team(team_id),
    opened_year         INTEGER,
    closed_year         INTEGER,
    capacity            INTEGER,
    surface_type        VARCHAR(50),    -- grass, artificial, turf
    created_at          TIMESTAMP       NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMP       NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS ix_park_mlbam      ON baseball.park (park_mlbam_id);
CREATE INDEX IF NOT EXISTS ix_park_retro      ON baseball.park (park_retrosheet_id);
CREATE INDEX IF NOT EXISTS ix_park_home_team  ON baseball.park (home_team_id);
