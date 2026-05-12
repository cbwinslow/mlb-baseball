-- =============================================================================
-- Raw FanGraphs Batting Stats Table
-- Source: FanGraphs via pybaseball batting_stats()
-- Docs:   https://github.com/jldbc/pybaseball/blob/master/docs/batting_stats.md
--         https://www.fangraphs.com/library/
-- Notes:  Season-level batting stats for all players. Column set is very wide
--         (~330 columns). All columns returned by pybaseball are preserved.
--         Columns are stored as TEXT/NUMERIC to handle any schema changes
--         FanGraphs makes. The most common/stable columns are typed explicitly.
-- =============================================================================

CREATE TABLE IF NOT EXISTS raw.fangraphs_batting (
    -- -------------------------------------------------------------------------
    -- Identity
    -- -------------------------------------------------------------------------
    "IDfg"              INTEGER,        -- FanGraphs player ID
    "Season"            SMALLINT,       -- Season year
    "Name"              TEXT,           -- Player name
    "Team"              TEXT,           -- Team abbreviation
    "Age"               SMALLINT,
    "AgeRng"            TEXT,           -- Age range (e.g. 26-27 for multi-season)

    -- -------------------------------------------------------------------------
    -- Standard batting
    -- -------------------------------------------------------------------------
    "G"                 SMALLINT,
    "AB"                SMALLINT,
    "PA"                SMALLINT,       -- Plate appearances
    "H"                 SMALLINT,
    "1B"                SMALLINT,
    "2B"                SMALLINT,
    "3B"                SMALLINT,
    "HR"                SMALLINT,
    "R"                 SMALLINT,
    "RBI"               SMALLINT,
    "BB"                SMALLINT,
    "IBB"               SMALLINT,
    "SO"                SMALLINT,
    "HBP"               SMALLINT,
    "SF"                SMALLINT,
    "SH"                SMALLINT,
    "GDP"               SMALLINT,
    "SB"                SMALLINT,
    "CS"                SMALLINT,
    "AVG"               NUMERIC(6,3),

    -- -------------------------------------------------------------------------
    -- Advanced / rate stats
    -- -------------------------------------------------------------------------
    "BB%"               NUMERIC(8,4),
    "K%"                NUMERIC(8,4),
    "BB/K"              NUMERIC(8,4),
    "OBP"               NUMERIC(6,3),
    "SLG"               NUMERIC(6,3),
    "OPS"               NUMERIC(6,3),
    "ISO"               NUMERIC(6,3),
    "Spd"               NUMERIC(6,2),   -- Speed score
    "BABIP"             NUMERIC(6,3),
    "UBR"               NUMERIC(8,2),
    "wRC"               NUMERIC(8,1),
    "wRAA"              NUMERIC(8,2),
    "wOBA"              NUMERIC(6,3),
    "wRC+"              NUMERIC(8,1),
    "WAR"               NUMERIC(7,2),

    -- -------------------------------------------------------------------------
    -- Batted ball
    -- -------------------------------------------------------------------------
    "GB%"               NUMERIC(7,4),
    "FB%"               NUMERIC(7,4),
    "LD%"               NUMERIC(7,4),
    "IFFB%"             NUMERIC(7,4),
    "HR/FB"             NUMERIC(7,4),
    "IFH%"              NUMERIC(7,4),
    "BUH%"              NUMERIC(7,4),
    "Pull%"             NUMERIC(7,4),
    "Cent%"             NUMERIC(7,4),
    "Oppo%"             NUMERIC(7,4),
    "Soft%"             NUMERIC(7,4),
    "Med%"              NUMERIC(7,4),
    "Hard%"             NUMERIC(7,4),

    -- -------------------------------------------------------------------------
    -- Plate discipline
    -- -------------------------------------------------------------------------
    "O-Swing%"          NUMERIC(7,4),
    "Z-Swing%"          NUMERIC(7,4),
    "Swing%"            NUMERIC(7,4),
    "O-Contact%"        NUMERIC(7,4),
    "Z-Contact%"        NUMERIC(7,4),
    "Contact%"          NUMERIC(7,4),
    "Zone%"             NUMERIC(7,4),
    "F-Strike%"         NUMERIC(7,4),
    "SwStr%"            NUMERIC(7,4),
    "CStr%"             NUMERIC(7,4),
    "CSW%"              NUMERIC(7,4),

    -- -------------------------------------------------------------------------
    -- Statcast/advanced (FanGraphs enrichment)
    -- -------------------------------------------------------------------------
    "EV"                NUMERIC(7,2),   -- Average exit velocity
    "LA"                NUMERIC(7,2),   -- Average launch angle
    "Barrels"           SMALLINT,
    "Barrel%"           NUMERIC(7,4),
    "maxEV"             NUMERIC(7,2),
    "HardHit"           SMALLINT,
    "HardHit%"          NUMERIC(7,4),
    "Events"            SMALLINT,
    "xBA"               NUMERIC(6,3),
    "xSLG"              NUMERIC(6,3),
    "xwOBA"             NUMERIC(6,3),
    "xISO"              NUMERIC(6,3),

    -- -------------------------------------------------------------------------
    -- Win probability
    -- -------------------------------------------------------------------------
    "WPA"               NUMERIC(8,3),
    "-WPA"              NUMERIC(8,3),
    "+WPA"              NUMERIC(8,3),
    "RE24"              NUMERIC(8,2),
    "REW"               NUMERIC(8,2),
    "pLI"               NUMERIC(7,3),
    "phLI"              NUMERIC(7,3),
    "PH"                SMALLINT,
    "WPA/LI"            NUMERIC(8,3),
    "Clutch"            NUMERIC(7,2),

    -- -------------------------------------------------------------------------
    -- Catch-all for any additional FanGraphs columns not listed above
    -- (stored via jsonb sidecar if schema changes)
    -- -------------------------------------------------------------------------
    _extra_fields       JSONB,          -- Any extra columns not explicitly mapped

    -- -------------------------------------------------------------------------
    -- Audit
    -- -------------------------------------------------------------------------
    _ingested_at        TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_file        TEXT
);

COMMENT ON TABLE raw.fangraphs_batting IS
    'Raw FanGraphs batting stats via pybaseball batting_stats(). '
    'Source: https://www.fangraphs.com. ~330 columns total; common ones typed explicitly.';
