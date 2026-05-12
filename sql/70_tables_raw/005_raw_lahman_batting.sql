-- =============================================================================
-- Raw Lahman Database - Batting Table
-- Source: Sean Lahman Baseball Database (seanlahman.com)
-- Docs:   http://www.seanlahman.com/baseball-archive/statistics/
--         http://www.seanlahman.com/files/database/readme2023.txt
-- Via:    pybaseball lahman module or direct CSV download
-- Notes:  Season-level batting stats for all players. One row per player
--         per season per stint (team).
-- =============================================================================

CREATE TABLE IF NOT EXISTS raw.lahman_batting (
    playerID        TEXT,           -- Lahman player ID
    yearID          SMALLINT,       -- Season year
    stint           SMALLINT,       -- Player stint number (1 = first team of season)
    teamID          CHAR(3),        -- Lahman 3-char team code
    lgID            CHAR(2),        -- League: AL, NL, FL (Federal), etc.
    G               SMALLINT,       -- Games played
    AB              SMALLINT,       -- At bats
    R               SMALLINT,       -- Runs
    H               SMALLINT,       -- Hits
    "2B"            SMALLINT,       -- Doubles
    "3B"            SMALLINT,       -- Triples
    HR              SMALLINT,       -- Home runs
    RBI             SMALLINT,       -- Runs batted in
    SB              SMALLINT,       -- Stolen bases
    CS              SMALLINT,       -- Caught stealing
    BB              SMALLINT,       -- Base on balls (walks)
    SO              SMALLINT,       -- Strikeouts
    IBB             SMALLINT,       -- Intentional walks
    HBP             SMALLINT,       -- Hit by pitch
    SH              SMALLINT,       -- Sacrifice hits
    SF              SMALLINT,       -- Sacrifice flies
    GIDP            SMALLINT,       -- Grounded into double plays
    -- -------------------------------------------------------------------------
    -- Audit
    -- -------------------------------------------------------------------------
    _ingested_at    TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_file    TEXT
);

COMMENT ON TABLE raw.lahman_batting IS
    'Raw Lahman DB batting table - season stats per player per stint. '
    'Source: http://www.seanlahman.com/baseball-archive/statistics/';
