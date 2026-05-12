-- =============================================================================
-- Raw Lahman Database - FieldingPost Table
-- Source: Sean Lahman Baseball Database
-- =============================================================================

CREATE TABLE IF NOT EXISTS raw.lahman_fielding_post (
    playerID        TEXT,
    yearID          SMALLINT,
    teamID          CHAR(3),
    lgID            CHAR(2),
    round           TEXT,
    POS             TEXT,
    G               SMALLINT,
    GS              SMALLINT,
    InnOuts         INTEGER,
    PO              SMALLINT,
    A               SMALLINT,
    E               SMALLINT,
    DP              SMALLINT,
    TP              SMALLINT,       -- Triple plays
    PB              SMALLINT,
    SB              SMALLINT,
    CS              SMALLINT,
    _ingested_at    TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_file    TEXT
);

COMMENT ON TABLE raw.lahman_fielding_post IS 'Raw Lahman DB FieldingPost - postseason fielding.';
