-- =============================================================================
-- Raw Lahman Database - People (Player Biographical) Table
-- Source: Sean Lahman Baseball Database
-- Notes:  Formerly called 'Master'. Contains cross-reference IDs to
--         Retrosheet, MLBAM, Baseball Reference, FanGraphs, etc.
-- =============================================================================

CREATE TABLE IF NOT EXISTS raw.lahman_people (
    playerID        TEXT,           -- Lahman player ID
    birthYear       SMALLINT,
    birthMonth      SMALLINT,
    birthDay        SMALLINT,
    birthCountry    TEXT,
    birthState      TEXT,
    birthCity       TEXT,
    deathYear       SMALLINT,
    deathMonth      SMALLINT,
    deathDay        SMALLINT,
    deathCountry    TEXT,
    deathState      TEXT,
    deathCity       TEXT,
    nameFirst       TEXT,
    nameLast        TEXT,
    nameGiven       TEXT,
    weight          SMALLINT,       -- lbs
    height          SMALLINT,       -- inches
    bats            CHAR(1),        -- R, L, B
    throws          CHAR(1),        -- R, L
    debut           DATE,           -- MLB debut date
    finalGame       DATE,           -- Final MLB game date
    retroID         TEXT,           -- Retrosheet player ID
    bbrefID         TEXT,           -- Baseball Reference player ID
    deathDate       DATE,
    birthDate       DATE,
    _ingested_at    TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_file    TEXT
);

COMMENT ON TABLE raw.lahman_people IS
    'Raw Lahman DB People table (biographical data and cross-reference IDs).';
