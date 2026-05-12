-- =============================================================================
-- Raw Lahman Database - AllStarFull Table
-- Source: Sean Lahman Baseball Database
-- =============================================================================

CREATE TABLE IF NOT EXISTS raw.lahman_allstar (
    playerID        TEXT,
    yearID          SMALLINT,
    gameNum         SMALLINT,       -- Game number within year (some years had 2 ASGs)
    gameID          TEXT,           -- Retrosheet game ID for All-Star game
    teamID          CHAR(3),
    lgID            CHAR(2),
    GP              SMALLINT,       -- 1 if played in game
    startingPos     SMALLINT,       -- Starting position (NULL if did not start)
    _ingested_at    TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_file    TEXT
);

COMMENT ON TABLE raw.lahman_allstar IS 'Raw Lahman DB AllStarFull table.';
