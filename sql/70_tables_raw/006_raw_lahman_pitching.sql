-- =============================================================================
-- Raw Lahman Database - Pitching Table
-- Source: Sean Lahman Baseball Database
-- =============================================================================

CREATE TABLE IF NOT EXISTS raw.lahman_pitching (
    playerID        TEXT,
    yearID          SMALLINT,
    stint           SMALLINT,
    teamID          CHAR(3),
    lgID            CHAR(2),
    W               SMALLINT,       -- Wins
    L               SMALLINT,       -- Losses
    G               SMALLINT,       -- Games
    GS              SMALLINT,       -- Games started
    CG              SMALLINT,       -- Complete games
    SHO             SMALLINT,       -- Shutouts
    SV              SMALLINT,       -- Saves
    IPouts          INTEGER,        -- Outs pitched (IP * 3)
    H               SMALLINT,       -- Hits allowed
    ER              SMALLINT,       -- Earned runs
    HR              SMALLINT,       -- Home runs allowed
    BB              SMALLINT,       -- Walks
    SO              SMALLINT,       -- Strikeouts
    BAOpp           NUMERIC(6,3),   -- Opponent batting average
    ERA             NUMERIC(6,2),   -- Earned run average
    IBB             SMALLINT,       -- Intentional walks
    WP              SMALLINT,       -- Wild pitches
    HBP             SMALLINT,       -- Batters hit by pitch
    BK              SMALLINT,       -- Balks
    BFP             INTEGER,        -- Batters faced
    GF              SMALLINT,       -- Games finished
    R               SMALLINT,       -- Runs allowed
    SH              SMALLINT,       -- Sacrifice hits allowed
    SF              SMALLINT,       -- Sacrifice flies allowed
    GIDP            SMALLINT,       -- Grounded into double plays induced
    _ingested_at    TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_file    TEXT
);

COMMENT ON TABLE raw.lahman_pitching IS 'Raw Lahman DB pitching table.';
