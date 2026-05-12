-- =============================================================================
-- Raw Lahman Database - Parks Table
-- Source: Sean Lahman Baseball Database
-- =============================================================================

CREATE TABLE IF NOT EXISTS raw.lahman_parks (
    parkalias       TEXT,           -- Park alias code used in team/game records
    parkname        TEXT,           -- Full park name
    parkcity        TEXT,
    parkstate       TEXT,
    country         TEXT,
    parkid          TEXT,           -- Retrosheet park code
    _ingested_at    TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_file    TEXT
);

COMMENT ON TABLE raw.lahman_parks IS 'Raw Lahman DB Parks table.';
