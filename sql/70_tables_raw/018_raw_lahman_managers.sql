-- =============================================================================
-- Raw Lahman Database - Managers Table
-- Source: Sean Lahman Baseball Database
-- =============================================================================

CREATE TABLE IF NOT EXISTS raw.lahman_managers (
    playerID        TEXT,
    yearID          SMALLINT,
    teamID          CHAR(3),
    lgID            CHAR(2),
    inseason        SMALLINT,       -- Sequence if multiple managers in season
    G               SMALLINT,
    W               SMALLINT,
    L               SMALLINT,
    rank            SMALLINT,       -- Final standing
    plyrMgr         CHAR(1),        -- Y if player-manager
    _ingested_at    TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_file    TEXT
);

CREATE TABLE IF NOT EXISTS raw.lahman_managers_half (
    playerID        TEXT,
    yearID          SMALLINT,
    teamID          CHAR(3),
    lgID            CHAR(2),
    inseason        SMALLINT,
    half            SMALLINT,       -- 1 or 2 (split-season years)
    G               SMALLINT,
    W               SMALLINT,
    L               SMALLINT,
    rank            SMALLINT,
    _ingested_at    TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_file    TEXT
);

COMMENT ON TABLE raw.lahman_managers IS 'Raw Lahman DB Managers table.';
COMMENT ON TABLE raw.lahman_managers_half IS 'Raw Lahman DB ManagersHalf table (split-season standings).';
