-- =============================================================
-- 25_raw_espn.sql
-- RAW ESPN data tables
-- Source: https://site.api.espn.com/apis/site/v2/sports/baseball/mlb
-- Schema: raw
-- Tables: raw.espn_events, raw.espn_competitions, raw.espn_teams,
--         raw.espn_venues, raw.espn_broadcasts, raw.espn_odds
-- NOTE:   All fields from the official ESPN API endpoints
--         are preserved here exactly as returned.
-- =============================================================

-- -----------------------------------------------------------
-- raw.espn_events
-- /scoreboard endpoint - event information
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw.espn_events (
    id                    TEXT         NOT NULL PRIMARY KEY,
    uid                   TEXT,
    date                  TIMESTAMPTZ,
    name                  TEXT,
    short_name            TEXT,
    season_year           INTEGER,
    season_type           INTEGER,
    season_slug           TEXT,
    week                  INTEGER,
    season_display_name   TEXT,
    -- ingestion metadata
    source_url            TEXT,
    loaded_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_espn_events_date     ON raw.espn_events (date);
CREATE INDEX IF NOT EXISTS ix_espn_events_season   ON raw.espn_events (season_year, season_type);

-- -----------------------------------------------------------
-- raw.espn_competitions
-- /scoreboard endpoint - competition information (one per event)
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw.espn_competitions (
    id                    TEXT         NOT NULL PRIMARY KEY,
    uid                   TEXT,
    event_id              TEXT         NOT NULL REFERENCES raw.espn_events(id),
    date                  TIMESTAMPTZ,
    attendance            INTEGER,
    venue_id              TEXT,
    -- ingestion metadata
    source_url            TEXT,
    loaded_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_espn_competitions_event_id ON raw.espn_competitions (event_id);
CREATE INDEX IF NOT EXISTS ix_espn_competitions_venue_id ON raw.espn_competitions (venue_id);

-- -----------------------------------------------------------
-- raw.espn_teams
-- Team information from competitions
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw.espn_teams (
    id                    TEXT         NOT NULL,
    competition_id        TEXT         NOT NULL REFERENCES raw.espn_competitions(id),
    uid                   TEXT,
    home_away             TEXT,        -- home / away
    winner                BOOLEAN,
    score                 INTEGER,
    team_id               TEXT,
    team_uid              TEXT,
    team_slug             TEXT,
    team_location         TEXT,
    team_name             TEXT,
    team_abbreviation     TEXT,
    team_display_name     TEXT,
    team_short_display_name TEXT,
    -- ingestion metadata
    source_url            TEXT,
    loaded_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_espn_teams_competition_id ON raw.espn_teams (competition_id);
CREATE INDEX IF NOT EXISTS ix_espn_teams_team_id ON raw.espn_teams (team_id);
CREATE UNIQUE INDEX IF NOT EXISTS uidx_espn_teams_competition_home_away ON raw.espn_teams (competition_id, home_away);

-- -----------------------------------------------------------
-- raw.espn_venues
-- Venue information from competitions
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw.espn_venues (
    id                    TEXT         NOT NULL PRIMARY KEY,
    full_name             TEXT,
    -- ingestion metadata
    source_url            TEXT,
    loaded_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- -----------------------------------------------------------
-- raw.espn_broadcasts
-- Broadcast information from competitions
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw.espn_broadcasts (
    id                    TEXT         NOT NULL,
    competition_id        TEXT         NOT NULL REFERENCES raw.espn_competitions(id),
    name                  TEXT,
    market                TEXT,
    -- ingestion metadata
    source_url            TEXT,
    loaded_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_espn_broadcasts_competition_id ON raw.espn_broadcasts (competition_id);

-- -----------------------------------------------------------
-- raw.espn_odds
-- Odds information from competitions (if available)
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw.espn_odds (
    id                    TEXT         NOT NULL,
    competition_id        TEXT         NOT NULL REFERENCES raw.espn_competitions(id),
    provider_id           TEXT,
    provider_name         TEXT,
    details               TEXT,
    -- ingestion metadata
    source_url            TEXT,
    loaded_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_espn_odds_competition_id ON raw.espn_odds (competition_id);