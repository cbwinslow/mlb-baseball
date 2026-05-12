-- =============================================================================
-- Raw Baseball Reference Pitching Stats Table
-- Source: Baseball Reference via pybaseball pitching_stats_bref() /
--         pitching_stats_range()
-- =============================================================================

CREATE TABLE IF NOT EXISTS raw.bbref_pitching (
    bbref_id            TEXT,
    "Name"              TEXT,
    "Age"               SMALLINT,
    "Season"            SMALLINT,
    "Team"              TEXT,
    "Tm"                TEXT,
    "Lg"                TEXT,
    "W"                 SMALLINT,
    "L"                 SMALLINT,
    "W-L%"              NUMERIC(6,3),
    "ERA"               NUMERIC(6,2),
    "G"                 SMALLINT,
    "GS"                SMALLINT,
    "GF"                SMALLINT,
    "CG"                SMALLINT,
    "SHO"               SMALLINT,
    "SV"                SMALLINT,
    "IP"                NUMERIC(7,1),
    "H"                 SMALLINT,
    "R"                 SMALLINT,
    "ER"                SMALLINT,
    "HR"                SMALLINT,
    "BB"                SMALLINT,
    "IBB"               SMALLINT,
    "SO"                SMALLINT,
    "HBP"               SMALLINT,
    "BK"                SMALLINT,
    "WP"                SMALLINT,
    "BF"                INTEGER,
    "ERA+"              SMALLINT,
    "FIP"               NUMERIC(6,2),
    "WHIP"              NUMERIC(6,3),
    "H9"                NUMERIC(6,2),
    "HR9"               NUMERIC(6,2),
    "BB9"               NUMERIC(6,2),
    "SO9"               NUMERIC(6,2),
    "SO/W"              NUMERIC(6,2),
    "RAR"               NUMERIC(7,1),
    "WAR"               NUMERIC(7,2),
    _ingested_at        TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_file        TEXT
);

COMMENT ON TABLE raw.bbref_pitching IS
    'Raw Baseball Reference pitching stats via pybaseball.';
