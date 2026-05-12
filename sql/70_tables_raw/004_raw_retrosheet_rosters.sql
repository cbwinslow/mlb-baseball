-- =============================================================================
-- Raw Retrosheet Roster Table
-- Source: Retrosheet (.ROS roster files and player register)
-- Docs:   https://www.retrosheet.org/eventfile.htm (start/sub records)
--         https://www.retrosheet.org/register.htm
-- Notes:  Covers both start/sub records from event files and the full player
--         register. Batting/throwing hand from .ROS files preserved.
-- =============================================================================

CREATE TABLE IF NOT EXISTS raw.retrosheet_rosters (
    -- -------------------------------------------------------------------------
    -- Player identity
    -- -------------------------------------------------------------------------
    player_id                   TEXT NOT NULL,      -- 8-char Retrosheet player ID (e.g. joner002)
    last_name                   TEXT,               -- Player last name
    first_name                  TEXT,               -- Player first name
    bats                        CHAR(1),            -- B=both, L=left, R=right
    throws                      CHAR(1),            -- L=left, R=right

    -- -------------------------------------------------------------------------
    -- Roster context
    -- -------------------------------------------------------------------------
    team_id                     CHAR(3),            -- Retrosheet 3-char team code
    season_year                 SMALLINT,           -- Season year this roster is for
    position                    TEXT,               -- Primary position code (if from .ROS)

    -- -------------------------------------------------------------------------
    -- From start/sub records in event files
    -- -------------------------------------------------------------------------
    game_id                     TEXT,               -- Game where this lineup entry appears
    batting_order               SMALLINT,           -- Batting order position (1-9, or 0 for DH-pitcher)
    fielding_position           SMALLINT,           -- Fielding position (1-9, 10=DH, 11=PH, 12=PR)
    home_team_flag              SMALLINT,           -- 0=visitor, 1=home
    record_type                 CHAR(5),            -- 'start' or 'sub'

    -- -------------------------------------------------------------------------
    -- Audit
    -- -------------------------------------------------------------------------
    _ingested_at                TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_file                TEXT
);

COMMENT ON TABLE raw.retrosheet_rosters IS
    'Raw Retrosheet roster data from .ROS files and start/sub event records. '
    'Source: https://www.retrosheet.org/';
