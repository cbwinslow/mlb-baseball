-- ============================================================
-- 11_player_season.sql
-- Player season batting statistics aggregate
-- Schema: baseball
-- Mirrors: baseball.db.models.PlayerSeason
-- ============================================================

CREATE TABLE IF NOT EXISTS baseball.player_season (
    player_season_id    SERIAL          PRIMARY KEY,
    player_id           INTEGER         NOT NULL REFERENCES baseball.player(player_id),
    season              INTEGER         NOT NULL,
    source              VARCHAR(20)     NOT NULL,   -- mlb, retrosheet, fangraphs
    games_played        INTEGER,
    plate_appearances   INTEGER,
    at_bats             INTEGER,
    hits                INTEGER,
    doubles             INTEGER,
    triples             INTEGER,
    home_runs           INTEGER,
    rbis                INTEGER,
    runs                INTEGER,
    walks               INTEGER,
    strikeouts          INTEGER,
    batting_avg         NUMERIC(5,3),
    on_base_pct         NUMERIC(5,3),
    slugging_pct        NUMERIC(5,3),
    ops                 NUMERIC(5,3),
    war                 NUMERIC(6,2),
    created_at          TIMESTAMP       NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMP       NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_player_season_source UNIQUE (player_id, season, source)
);

-- Indexes
CREATE INDEX IF NOT EXISTS ix_player_season        ON baseball.player_season (season, player_id);
CREATE INDEX IF NOT EXISTS ix_player_season_source ON baseball.player_season (source);
