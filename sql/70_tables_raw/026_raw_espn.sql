-- ============================================================
-- 026_raw_espn.sql
-- RAW ESPN API data tables
-- Source: ESPN hidden API (site.api.espn.com)
-- Schema: raw
-- Tables: raw.espn_scoreboard, raw.espn_game_summary,
--         raw.espn_teams, raw.espn_rosters,
--         raw.espn_athletes, raw.espn_standings,
--         raw.espn_news, raw.espn_load_batches
-- NOTE: ESPN API is unofficial and subject to change.
--       Full JSONB payload is preserved alongside scalar
--       identifiers. Do not cast ESPN IDs to integers.
-- ============================================================

-- ------------------------------------------------------------
-- raw.espn_scoreboard
-- /apis/site/v2/sports/baseball/mlb/scoreboard endpoint
-- One row per game entry from the scoreboard response.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw.espn_scoreboard (
    load_id          UUID          NOT NULL,
    event_id         TEXT          NOT NULL,
    game_date        TIMESTAMPTZ,
    season_year      INTEGER,
    season_type      INTEGER,       -- 1=preseason, 2=regular, 3=postseason
    status_name      TEXT,          -- STATUS_FINAL, STATUS_IN_PROGRESS, etc.
    home_team_id     TEXT,
    away_team_id     TEXT,
    home_score       INTEGER,
    away_score       INTEGER,
    venue_name       TEXT,
    query_date       DATE,
    payload          JSONB,         -- Full event object from scoreboard response
    retrieved_at     TIMESTAMPTZ   NOT NULL DEFAULT now(),
    PRIMARY KEY (load_id, event_id)
);

CREATE INDEX IF NOT EXISTS idx_espn_scoreboard_event_id   ON raw.espn_scoreboard (event_id);
CREATE INDEX IF NOT EXISTS idx_espn_scoreboard_game_date  ON raw.espn_scoreboard (game_date);
CREATE INDEX IF NOT EXISTS idx_espn_scoreboard_season     ON raw.espn_scoreboard (season_year, season_type);

-- ------------------------------------------------------------
-- raw.espn_game_summary
-- /apis/site/v2/sports/baseball/mlb/summary endpoint
-- One row per event; preserves boxscore, plays, and win prob.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw.espn_game_summary (
    load_id          UUID          NOT NULL,
    event_id         TEXT          NOT NULL,
    game_date        DATE,
    status_name      TEXT,
    home_team_id     TEXT,
    away_team_id     TEXT,
    home_score       INTEGER,
    away_score       INTEGER,
    boxscore         JSONB,         -- Boxscore section payload
    plays            JSONB,         -- Play-by-play array payload
    win_probability  JSONB,         -- Win probability array payload
    full_payload     JSONB,         -- Complete summary response
    retrieved_at     TIMESTAMPTZ   NOT NULL DEFAULT now(),
    PRIMARY KEY (load_id, event_id)
);

CREATE INDEX IF NOT EXISTS idx_espn_game_summary_event_id  ON raw.espn_game_summary (event_id);
CREATE INDEX IF NOT EXISTS idx_espn_game_summary_date      ON raw.espn_game_summary (game_date);

-- ------------------------------------------------------------
-- raw.espn_teams
-- /apis/site/v2/sports/baseball/mlb/teams endpoint
-- One row per team per load batch.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw.espn_teams (
    load_id              UUID    NOT NULL,
    team_id              TEXT    NOT NULL,
    uid                  TEXT,
    slug                 TEXT,
    abbreviation         TEXT,
    display_name         TEXT,
    short_display_name   TEXT,
    location             TEXT,
    name                 TEXT,
    color                TEXT,   -- Primary color hex
    alternate_color      TEXT,
    payload              JSONB,  -- Full team object
    retrieved_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (load_id, team_id)
);

CREATE INDEX IF NOT EXISTS idx_espn_teams_team_id      ON raw.espn_teams (team_id);
CREATE INDEX IF NOT EXISTS idx_espn_teams_abbreviation ON raw.espn_teams (abbreviation);

-- ------------------------------------------------------------
-- raw.espn_rosters
-- /apis/site/v2/sports/baseball/mlb/teams/{id}/roster endpoint
-- One row per athlete per team per load batch.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw.espn_rosters (
    load_id         UUID    NOT NULL,
    team_id         TEXT    NOT NULL,
    athlete_id      TEXT    NOT NULL,
    display_name    TEXT,
    jersey          TEXT,
    position_abbrev TEXT,
    status_type     TEXT,   -- Active, Injured, etc.
    payload         JSONB,  -- Full athlete roster entry object
    retrieved_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (load_id, team_id, athlete_id)
);

CREATE INDEX IF NOT EXISTS idx_espn_rosters_team_id    ON raw.espn_rosters (team_id);
CREATE INDEX IF NOT EXISTS idx_espn_rosters_athlete_id ON raw.espn_rosters (athlete_id);

-- ------------------------------------------------------------
-- raw.espn_athletes
-- /apis/site/v2/sports/baseball/mlb/athletes/{id} endpoint
-- One row per athlete per load batch.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw.espn_athletes (
    load_id          UUID      NOT NULL,
    athlete_id       TEXT      NOT NULL,
    uid              TEXT,
    display_name     TEXT,
    short_name       TEXT,
    weight           INTEGER,
    height           INTEGER,
    age              INTEGER,
    date_of_birth    DATE,
    birth_city       TEXT,
    birth_state      TEXT,
    birth_country    TEXT,
    college          TEXT,
    position_abbrev  TEXT,
    active           BOOLEAN,
    payload          JSONB,    -- Full athlete object
    retrieved_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (load_id, athlete_id)
);

CREATE INDEX IF NOT EXISTS idx_espn_athletes_athlete_id   ON raw.espn_athletes (athlete_id);
CREATE INDEX IF NOT EXISTS idx_espn_athletes_display_name ON raw.espn_athletes (display_name);

-- ------------------------------------------------------------
-- raw.espn_standings
-- /apis/v2/sports/baseball/mlb/standings endpoint
-- One row per team per season per load batch.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw.espn_standings (
    load_id       UUID      NOT NULL,
    season_year   INTEGER   NOT NULL,
    season_type   INTEGER   NOT NULL,
    team_id       TEXT      NOT NULL,
    team_abbrev   TEXT,
    wins          INTEGER,
    losses        INTEGER,
    win_pct       NUMERIC(5,3),
    games_back    NUMERIC(5,1),
    streak        TEXT,
    payload       JSONB,    -- Full standings entry object
    retrieved_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (load_id, season_year, season_type, team_id)
);

CREATE INDEX IF NOT EXISTS idx_espn_standings_team_id ON raw.espn_standings (team_id);
CREATE INDEX IF NOT EXISTS idx_espn_standings_season  ON raw.espn_standings (season_year, season_type);

-- ------------------------------------------------------------
-- raw.espn_news
-- /apis/v3/now/story/_/page/mlb news endpoint
-- One row per news article per load batch.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw.espn_news (
    load_id          UUID    NOT NULL,
    article_id       TEXT    NOT NULL,
    headline         TEXT,
    description      TEXT,
    published_at     TIMESTAMPTZ,
    last_modified_at TIMESTAMPTZ,
    article_url      TEXT,
    payload          JSONB,  -- Full article object
    retrieved_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (load_id, article_id)
);

CREATE INDEX IF NOT EXISTS idx_espn_news_article_id   ON raw.espn_news (article_id);
CREATE INDEX IF NOT EXISTS idx_espn_news_published_at ON raw.espn_news (published_at);

-- ------------------------------------------------------------
-- raw.espn_load_batches
-- Metadata table tracking each ESPN API load operation.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw.espn_load_batches (
    load_id        UUID        NOT NULL PRIMARY KEY DEFAULT gen_random_uuid(),
    endpoint_family TEXT       NOT NULL,  -- scoreboard/game_summary/teams/rosters/athletes/standings/news
    request_url    TEXT,
    request_params JSONB,
    rows_loaded    INTEGER,
    loaded_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    status         TEXT,       -- success / failed / partial
    error_message  TEXT
);

CREATE INDEX IF NOT EXISTS idx_espn_load_batches_endpoint ON raw.espn_load_batches (endpoint_family);
CREATE INDEX IF NOT EXISTS idx_espn_load_batches_loaded_at ON raw.espn_load_batches (loaded_at);
