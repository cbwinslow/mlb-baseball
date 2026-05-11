-- ============================================================
-- 12_pitcher_season.sql
-- Pitcher season statistics aggregate
-- Schema: baseball
-- Mirrors: baseball.db.models.PitcherSeason
-- ============================================================

CREATE TABLE IF NOT EXISTS baseball.pitcher_season (
    pitcher_season_id   SERIAL          PRIMARY KEY,
    player_id           INTEGER         NOT NULL REFERENCES baseball.player(player_id),
    season              INTEGER         NOT NULL,
    source              VARCHAR(20)     NOT NULL,   -- mlb, retrosheet, fangraphs
    team_id             INTEGER         REFERENCES baseball.team(team_id),
    games               INTEGER,
    games_started       INTEGER,
    innings_pitched     NUMERIC(6,1),
    wins                INTEGER,
    losses              INTEGER,
    saves               INTEGER,
    earned_run_avg      NUMERIC(5,2),
    strikeouts          INTEGER,
    walks               INTEGER,
    hits_allowed        INTEGER,
    home_runs_allowed   INTEGER,
    whip                NUMERIC(5,2),
    fip                 NUMERIC(5,2),
    war                 NUMERIC(6,2),
    created_at          TIMESTAMP       NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMP       NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_pitcher_season_source UNIQUE (player_id, season, source)
);

-- Indexes
CREATE INDEX IF NOT EXISTS ix_pitcher_season        ON baseball.pitcher_season (season, player_id);
CREATE INDEX IF NOT EXISTS ix_pitcher_season_team   ON baseball.pitcher_season (team_id);
CREATE INDEX IF NOT EXISTS ix_pitcher_season_source ON baseball.pitcher_season (source);
