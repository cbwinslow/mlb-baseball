-- =============================================================================
-- Raw Baseball Reference Batting Stats Table
-- Source: Baseball Reference via pybaseball batting_stats_bref() /
--         batting_stats_range()
-- Docs:   https://github.com/jldbc/pybaseball/blob/master/docs/batting_stats_bref.md
-- =============================================================================

CREATE TABLE IF NOT EXISTS raw.bbref_batting (
    -- -------------------------------------------------------------------------
    -- Identity
    -- -------------------------------------------------------------------------
    bbref_id            TEXT,           -- Baseball Reference player ID
    "Name"              TEXT,
    "Age"               SMALLINT,
    "Season"            SMALLINT,       -- Added by pybaseball
    "Team"              TEXT,           -- Also appears as Tm in raw CSV
    "Tm"                TEXT,
    "Lg"                TEXT,

    -- -------------------------------------------------------------------------
    -- Standard batting (matching bbref column names exactly)
    -- -------------------------------------------------------------------------
    "G"                 SMALLINT,
    "PA"                SMALLINT,
    "AB"                SMALLINT,
    "R"                 SMALLINT,
    "H"                 SMALLINT,
    "2B"                SMALLINT,
    "3B"                SMALLINT,
    "HR"                SMALLINT,
    "RBI"               SMALLINT,
    "SB"                SMALLINT,
    "CS"                SMALLINT,
    "BB"                SMALLINT,
    "SO"                SMALLINT,
    "BA"                NUMERIC(6,3),
    "OBP"               NUMERIC(6,3),
    "SLG"               NUMERIC(6,3),
    "OPS"               NUMERIC(6,3),
    "OPS+"              SMALLINT,       -- OPS+ (park/league adjusted)
    "TB"                SMALLINT,       -- Total bases
    "GDP"               SMALLINT,
    "HBP"               SMALLINT,
    "SH"                SMALLINT,
    "SF"                SMALLINT,
    "IBB"               SMALLINT,
    "rOBA"              NUMERIC(6,3),   -- bbref re-weighted OBA
    "Rbat"              NUMERIC(7,1),   -- Batting runs above average
    "Rbaser"            NUMERIC(7,1),   -- Baserunning runs
    "Rdp"               NUMERIC(7,1),   -- Double play runs
    "Rfield"            NUMERIC(7,1),   -- Fielding runs
    "Rpos"              NUMERIC(7,1),   -- Positional adjustment
    "RAA"               NUMERIC(7,1),   -- Runs above average
    "WAA"               NUMERIC(7,2),   -- Wins above average
    "Rrep"              NUMERIC(7,1),   -- Replacement-level runs
    "RAR"               NUMERIC(7,1),   -- Runs above replacement
    "WAR"               NUMERIC(7,2),   -- Baseball Reference WAR
    "waaWL%"            NUMERIC(7,4),   -- Team winning % with avg player
    "162WL%"            NUMERIC(7,4),   -- Team 162-game equivalent W-L%
    "oWAR"              NUMERIC(7,2),   -- Offensive WAR
    "dWAR"              NUMERIC(7,2),   -- Defensive WAR
    "oRAR"              NUMERIC(7,1),
    "Pos"               TEXT,           -- Primary positions played
    _ingested_at        TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_file        TEXT
);

COMMENT ON TABLE raw.bbref_batting IS
    'Raw Baseball Reference batting stats via pybaseball. '
    'Column names match bbref CSV export exactly.';
