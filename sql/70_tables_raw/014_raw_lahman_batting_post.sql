-- =============================================================================
-- Raw Lahman Database - BattingPost Table
-- Source: Sean Lahman Baseball Database
-- Notes:  Postseason batting stats. Same columns as lahman_batting.
-- =============================================================================

CREATE TABLE IF NOT EXISTS raw.lahman_batting_post (
    yearID          SMALLINT,
    round           TEXT,           -- Postseason round (e.g. WS, LCS, ALDS, NLDS, ALWC)
    playerID        TEXT,
    teamID          CHAR(3),
    lgID            CHAR(2),
    G               SMALLINT,
    AB              SMALLINT,
    R               SMALLINT,
    H               SMALLINT,
    "2B"            SMALLINT,
    "3B"            SMALLINT,
    HR              SMALLINT,
    RBI             SMALLINT,
    SB              SMALLINT,
    CS              SMALLINT,
    BB              SMALLINT,
    SO              SMALLINT,
    IBB             SMALLINT,
    HBP             SMALLINT,
    SH              SMALLINT,
    SF              SMALLINT,
    GIDP            SMALLINT,
    _ingested_at    TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_file    TEXT
);

COMMENT ON TABLE raw.lahman_batting_post IS 'Raw Lahman DB BattingPost - postseason batting.';
