-- =============================================================================
-- Raw Lahman Database - PitchingPost Table
-- Source: Sean Lahman Baseball Database
-- =============================================================================

CREATE TABLE IF NOT EXISTS raw.lahman_pitching_post (
    playerID        TEXT,
    yearID          SMALLINT,
    round           TEXT,
    teamID          CHAR(3),
    lgID            CHAR(2),
    W               SMALLINT,
    L               SMALLINT,
    G               SMALLINT,
    GS              SMALLINT,
    CG              SMALLINT,
    SHO             SMALLINT,
    SV              SMALLINT,
    IPouts          INTEGER,
    H               SMALLINT,
    ER              SMALLINT,
    HR              SMALLINT,
    BB              SMALLINT,
    SO              SMALLINT,
    BAOpp           NUMERIC(6,3),
    ERA             NUMERIC(6,2),
    IBB             SMALLINT,
    WP              SMALLINT,
    HBP             SMALLINT,
    BK              SMALLINT,
    BFP             INTEGER,
    GF              SMALLINT,
    R               SMALLINT,
    SH              SMALLINT,
    SF              SMALLINT,
    GIDP            SMALLINT,
    _ingested_at    TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_file    TEXT
);

COMMENT ON TABLE raw.lahman_pitching_post IS 'Raw Lahman DB PitchingPost - postseason pitching.';
