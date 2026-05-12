-- =============================================================================
-- Raw Lahman Database - Teams Table
-- Source: Sean Lahman Baseball Database
-- =============================================================================

CREATE TABLE IF NOT EXISTS raw.lahman_teams (
    yearID          SMALLINT,
    lgID            CHAR(2),
    teamID          CHAR(3),
    franchID        CHAR(3),        -- Franchise ID
    divID           CHAR(1),        -- Division: E, C, W
    Rank            SMALLINT,       -- Final division rank
    G               SMALLINT,       -- Games played
    Ghome           SMALLINT,       -- Home games
    W               SMALLINT,
    L               SMALLINT,
    DivWin          CHAR(1),        -- Y/N division winner
    WCWin           CHAR(1),        -- Y/N wild card winner
    LgWin           CHAR(1),        -- Y/N league pennant winner
    WSWin           CHAR(1),        -- Y/N World Series winner
    R               SMALLINT,       -- Runs scored
    AB              INTEGER,
    H               INTEGER,
    "2B"            SMALLINT,
    "3B"            SMALLINT,
    HR              SMALLINT,
    BB              SMALLINT,
    SO              INTEGER,
    SB              SMALLINT,
    CS              SMALLINT,
    HBP             SMALLINT,
    SF              SMALLINT,
    RA              SMALLINT,       -- Runs allowed
    ER              INTEGER,
    ERA             NUMERIC(6,2),
    CG              SMALLINT,
    SHO             SMALLINT,
    SV              SMALLINT,
    IPouts          INTEGER,
    HA              INTEGER,        -- Hits allowed
    HRA             SMALLINT,       -- HR allowed
    BBA             SMALLINT,       -- BB allowed
    SOA             INTEGER,        -- K allowed
    E               SMALLINT,
    DP              SMALLINT,
    FP              NUMERIC(6,3),   -- Fielding percentage
    name            TEXT,           -- Full team name
    park            TEXT,           -- Ballpark name
    attendance      INTEGER,
    BPF             SMALLINT,       -- Three-year park factor for batters
    PPF             SMALLINT,       -- Three-year park factor for pitchers
    teamIDBR        TEXT,           -- Baseball Reference team ID
    teamIDlahman45  TEXT,           -- Lahman 4.5 era ID
    teamIDretro     CHAR(3),        -- Retrosheet team ID
    _ingested_at    TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_file    TEXT
);

COMMENT ON TABLE raw.lahman_teams IS 'Raw Lahman DB Teams table - season-level team records.';
