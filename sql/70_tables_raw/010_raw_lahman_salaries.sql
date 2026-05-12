-- =============================================================================
-- Raw Lahman Database - Salaries Table
-- Source: Sean Lahman Baseball Database
-- =============================================================================

CREATE TABLE IF NOT EXISTS raw.lahman_salaries (
    yearID          SMALLINT,
    teamID          CHAR(3),
    lgID            CHAR(2),
    playerID        TEXT,
    salary          NUMERIC(12,2),  -- Annual salary in USD
    _ingested_at    TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_file    TEXT
);

COMMENT ON TABLE raw.lahman_salaries IS 'Raw Lahman DB Salaries table.';
