-- =============================================================================
-- Raw Baseball Reference Schedule and Game Results Table
-- Source: Baseball Reference via pybaseball schedule_and_record()
-- Docs:   https://github.com/jldbc/pybaseball/blob/master/docs/schedule_and_record.md
-- Notes:  One row per scheduled game for the queried team and season.
-- =============================================================================

CREATE TABLE IF NOT EXISTS raw.bbref_schedule (
    "Date"              TEXT,           -- Formatted date string (e.g. Monday, Apr 5)
    "Tm"                TEXT,           -- Team abbreviation
    "Home_Away"         TEXT,           -- @ for away, empty for home
    "Opp"               TEXT,           -- Opponent abbreviation
    "W/L"               TEXT,           -- W, L, W-wo, L-wo, tie
    "R"                 NUMERIC(6,1),   -- Runs scored (NULL if not played yet)
    "RA"                NUMERIC(6,1),   -- Runs allowed
    "Inn"               NUMERIC(6,1),   -- Innings played (9 unless extra)
    "W-L"               TEXT,           -- Team record after game (e.g. 5-3)
    "Rank"              SMALLINT,       -- Division rank
    "GB"                TEXT,           -- Games behind (text; may be '-' for first)
    "Win"               TEXT,           -- Winning pitcher name
    "Loss"              TEXT,           -- Losing pitcher name
    "Save"              TEXT,           -- Save pitcher name
    "Time"              TEXT,           -- Game time (H:MM)
    "D/N"               TEXT,           -- D=day, N=night
    "Attendance"        NUMERIC(8,0),
    "cLI"               NUMERIC(7,3),   -- Championship leverage index
    "Streak"            TEXT,           -- Win/loss streak
    "Orig_Scheduled"    TEXT,           -- Original scheduled date if postponed
    -- Metadata added by pybaseball
    season              SMALLINT,
    team                CHAR(3),
    _ingested_at        TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_file        TEXT
);

COMMENT ON TABLE raw.bbref_schedule IS
    'Raw Baseball Reference schedule & results via pybaseball schedule_and_record(). '
    'One row per game per team per season.';
