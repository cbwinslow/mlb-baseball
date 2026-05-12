-- =============================================================================
-- Raw Lahman Database - Fielding Table
-- Source: Sean Lahman Baseball Database
-- =============================================================================

CREATE TABLE IF NOT EXISTS raw.lahman_fielding (
    playerID        TEXT,
    yearID          SMALLINT,
    stint           SMALLINT,
    teamID          CHAR(3),
    lgID            CHAR(2),
    POS             TEXT,           -- Fielding position
    G               SMALLINT,       -- Games played at position
    GS              SMALLINT,       -- Games started at position
    InnOuts         INTEGER,        -- Time played in the field (in outs)
    PO              SMALLINT,       -- Putouts
    A               SMALLINT,       -- Assists
    E               SMALLINT,       -- Errors
    DP              SMALLINT,       -- Double plays
    PB              SMALLINT,       -- Passed balls (catchers only)
    WP              SMALLINT,       -- Wild pitches (catchers only)
    SB              SMALLINT,       -- Opponent stolen bases (catchers only)
    CS              SMALLINT,       -- Opponent caught stealing (catchers only)
    ZR              NUMERIC(7,3),   -- Zone rating (if available)
    _ingested_at    TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_file    TEXT
);

COMMENT ON TABLE raw.lahman_fielding IS 'Raw Lahman DB fielding table.';
