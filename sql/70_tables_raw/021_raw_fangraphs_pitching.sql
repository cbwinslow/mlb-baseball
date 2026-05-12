-- =============================================================================
-- Raw FanGraphs Pitching Stats Table
-- Source: FanGraphs via pybaseball pitching_stats()
-- Docs:   https://github.com/jldbc/pybaseball/blob/master/docs/pitching_stats.md
-- =============================================================================

CREATE TABLE IF NOT EXISTS raw.fangraphs_pitching (
    -- -------------------------------------------------------------------------
    -- Identity
    -- -------------------------------------------------------------------------
    "IDfg"              INTEGER,
    "Season"            SMALLINT,
    "Name"              TEXT,
    "Team"              TEXT,
    "Age"               SMALLINT,
    "AgeRng"            TEXT,

    -- -------------------------------------------------------------------------
    -- Standard pitching
    -- -------------------------------------------------------------------------
    "W"                 SMALLINT,
    "L"                 SMALLINT,
    "ERA"               NUMERIC(6,2),
    "G"                 SMALLINT,
    "GS"                SMALLINT,
    "CG"                SMALLINT,
    "ShO"               SMALLINT,
    "SV"                SMALLINT,
    "BS"                SMALLINT,
    "IP"                NUMERIC(7,1),
    "TBF"               INTEGER,        -- Total batters faced
    "H"                 SMALLINT,
    "R"                 SMALLINT,
    "ER"                SMALLINT,
    "HR"                SMALLINT,
    "BB"                SMALLINT,
    "IBB"               SMALLINT,
    "HBP"               SMALLINT,
    "WP"                SMALLINT,
    "BK"                SMALLINT,
    "SO"                SMALLINT,

    -- -------------------------------------------------------------------------
    -- Rate stats
    -- -------------------------------------------------------------------------
    "K/9"               NUMERIC(6,2),
    "BB/9"              NUMERIC(6,2),
    "K/BB"              NUMERIC(6,2),
    "H/9"               NUMERIC(6,2),
    "HR/9"              NUMERIC(6,2),
    "K%"                NUMERIC(8,4),
    "BB%"               NUMERIC(8,4),
    "K-BB%"             NUMERIC(8,4),
    "AVG"               NUMERIC(6,3),
    "WHIP"              NUMERIC(6,3),
    "BABIP"             NUMERIC(6,3),
    "LOB%"              NUMERIC(7,4),
    "FIP"               NUMERIC(6,2),
    "xFIP"              NUMERIC(6,2),
    "SIERA"             NUMERIC(6,2),
    "ERA-"              NUMERIC(7,1),   -- ERA- (park/league adjusted)
    "FIP-"              NUMERIC(7,1),
    "xFIP-"             NUMERIC(7,1),
    "WAR"               NUMERIC(7,2),
    "RAR"               NUMERIC(7,2),

    -- -------------------------------------------------------------------------
    -- Batted ball
    -- -------------------------------------------------------------------------
    "GB%"               NUMERIC(7,4),
    "FB%"               NUMERIC(7,4),
    "LD%"               NUMERIC(7,4),
    "IFFB%"             NUMERIC(7,4),
    "HR/FB"             NUMERIC(7,4),
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
    -- Statcast pitching metrics
    -- -------------------------------------------------------------------------
    "EV"                NUMERIC(7,2),
    "LA"                NUMERIC(7,2),
    "Barrels"           SMALLINT,
    "Barrel%"           NUMERIC(7,4),
    "maxEV"             NUMERIC(7,2),
    "HardHit"           SMALLINT,
    "HardHit%"          NUMERIC(7,4),
    "Events"            SMALLINT,
    "xERA"              NUMERIC(6,2),
    "xFIP"              NUMERIC(6,2),

    -- -------------------------------------------------------------------------
    -- Pitch mix (percentages)
    -- -------------------------------------------------------------------------
    "FA%"               NUMERIC(7,4),   -- Four-seam fastball
    "SI%"               NUMERIC(7,4),   -- Sinker
    "FC%"               NUMERIC(7,4),   -- Cutter
    "SL%"               NUMERIC(7,4),   -- Slider
    "CU%"               NUMERIC(7,4),   -- Curveball
    "CH%"               NUMERIC(7,4),   -- Changeup
    "FS%"               NUMERIC(7,4),   -- Splitter
    "KN%"               NUMERIC(7,4),   -- Knuckleball
    "XX%"               NUMERIC(7,4),   -- Unknown

    -- -------------------------------------------------------------------------
    -- Velocity by pitch type
    -- -------------------------------------------------------------------------
    "vFA"               NUMERIC(6,2),
    "vSI"               NUMERIC(6,2),
    "vFC"               NUMERIC(6,2),
    "vSL"               NUMERIC(6,2),
    "vCU"               NUMERIC(6,2),
    "vCH"               NUMERIC(6,2),
    "vFS"               NUMERIC(6,2),
    "vKN"               NUMERIC(6,2),

    -- -------------------------------------------------------------------------
    -- Win probability
    -- -------------------------------------------------------------------------
    "WPA"               NUMERIC(8,3),
    "RE24"              NUMERIC(8,2),
    "pLI"               NUMERIC(7,3),
    "Clutch"            NUMERIC(7,2),

    _extra_fields       JSONB,
    _ingested_at        TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_file        TEXT
);

COMMENT ON TABLE raw.fangraphs_pitching IS
    'Raw FanGraphs pitching stats via pybaseball pitching_stats(). '
    'Source: https://www.fangraphs.com.';
