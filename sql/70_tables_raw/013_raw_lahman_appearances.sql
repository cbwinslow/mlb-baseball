-- =============================================================================
-- Raw Lahman Database - Appearances Table
-- Source: Sean Lahman Baseball Database
-- Notes:  Games played at each position per player per season.
-- =============================================================================

CREATE TABLE IF NOT EXISTS raw.lahman_appearances (
    yearID          SMALLINT,
    teamID          CHAR(3),
    lgID            CHAR(2),
    playerID        TEXT,
    G_all           SMALLINT,       -- Total games (including DH, PH, PR)
    GS              SMALLINT,       -- Games started
    G_batting       SMALLINT,
    G_defense       SMALLINT,
    G_p             SMALLINT,       -- Games as pitcher
    G_c             SMALLINT,       -- Games as catcher
    G_1b            SMALLINT,
    G_2b            SMALLINT,
    G_3b            SMALLINT,
    G_ss            SMALLINT,
    G_lf            SMALLINT,
    G_cf            SMALLINT,
    G_rf            SMALLINT,
    G_of            SMALLINT,       -- Games as outfielder (any)
    G_dh            SMALLINT,
    G_ph            SMALLINT,
    G_pr            SMALLINT,
    _ingested_at    TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_file    TEXT
);

COMMENT ON TABLE raw.lahman_appearances IS 'Raw Lahman DB Appearances table.';
