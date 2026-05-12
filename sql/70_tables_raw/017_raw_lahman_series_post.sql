-- =============================================================================
-- Raw Lahman Database - SeriesPost Table
-- Source: Sean Lahman Baseball Database
-- =============================================================================

CREATE TABLE IF NOT EXISTS raw.lahman_series_post (
    yearID          SMALLINT,
    round           TEXT,           -- WS, LCS, ALDS, NLDS, etc.
    teamIDwinner    CHAR(3),
    lgIDwinner      CHAR(2),
    teamIDloser     CHAR(3),
    lgIDloser       CHAR(2),
    wins            SMALLINT,
    losses          SMALLINT,
    ties            SMALLINT,
    _ingested_at    TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_file    TEXT
);

COMMENT ON TABLE raw.lahman_series_post IS 'Raw Lahman DB SeriesPost - postseason series results.';
