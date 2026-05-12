-- =============================================================================
-- Raw Lahman Database - Awards Tables
-- Source: Sean Lahman Baseball Database
-- Notes:  Covers AwardsPlayers, AwardsManagers, AwardsSharePlayers,
--         AwardsShareManagers as separate tables.
-- =============================================================================

CREATE TABLE IF NOT EXISTS raw.lahman_awards_players (
    playerID        TEXT,
    awardID         TEXT,           -- Name of award
    yearID          SMALLINT,
    lgID            CHAR(2),
    tie             CHAR(1),        -- Y if tie
    notes           TEXT,
    _ingested_at    TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_file    TEXT
);

CREATE TABLE IF NOT EXISTS raw.lahman_awards_managers (
    playerID        TEXT,
    awardID         TEXT,
    yearID          SMALLINT,
    lgID            CHAR(2),
    tie             CHAR(1),
    notes           TEXT,
    _ingested_at    TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_file    TEXT
);

CREATE TABLE IF NOT EXISTS raw.lahman_awards_share_players (
    awardID         TEXT,
    yearID          SMALLINT,
    lgID            CHAR(2),
    playerID        TEXT,
    pointsWon       NUMERIC(8,1),   -- Points won in award voting
    pointsMax       NUMERIC(8,1),   -- Maximum points possible
    votesFirst      NUMERIC(8,1),   -- First-place votes received
    _ingested_at    TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_file    TEXT
);

CREATE TABLE IF NOT EXISTS raw.lahman_awards_share_managers (
    awardID         TEXT,
    yearID          SMALLINT,
    lgID            CHAR(2),
    playerID        TEXT,
    pointsWon       NUMERIC(8,1),
    pointsMax       NUMERIC(8,1),
    votesFirst      NUMERIC(8,1),
    _ingested_at    TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_file    TEXT
);

COMMENT ON TABLE raw.lahman_awards_players IS 'Raw Lahman DB Awards - Players.';
COMMENT ON TABLE raw.lahman_awards_managers IS 'Raw Lahman DB Awards - Managers.';
COMMENT ON TABLE raw.lahman_awards_share_players IS 'Raw Lahman DB Award voting shares - Players.';
COMMENT ON TABLE raw.lahman_awards_share_managers IS 'Raw Lahman DB Award voting shares - Managers.';
