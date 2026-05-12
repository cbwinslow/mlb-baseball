-- =============================================================================
-- Raw Player ID Cross-Reference Map
-- Source: Chadwick Bureau / pybaseball playerid_lookup() and playerid_reverse_lookup()
-- Docs:   https://github.com/jldbc/pybaseball/blob/master/docs/playerid_lookup.md
--         https://github.com/chadwickbureau/register
-- Notes:  Central cross-walk table linking player IDs across all data sources.
--         This is the most critical reference table for joining data across
--         Statcast (MLBAM), Retrosheet, Baseball Reference, FanGraphs, Lahman.
-- =============================================================================

CREATE TABLE IF NOT EXISTS raw.playerid_map (
    -- -------------------------------------------------------------------------
    -- Name
    -- -------------------------------------------------------------------------
    name_last           TEXT,
    name_first          TEXT,
    name_given          TEXT,           -- Given/full name if different

    -- -------------------------------------------------------------------------
    -- Cross-source IDs (all nullable since not every player has all IDs)
    -- -------------------------------------------------------------------------
    key_mlbam           INTEGER,        -- MLB Advanced Media (Statcast) player ID
    key_retro           TEXT,           -- Retrosheet player ID (8 chars)
    key_bbref           TEXT,           -- Baseball Reference player ID
    key_bbref_minors    TEXT,           -- Baseball Reference minor league ID
    key_fangraphs       INTEGER,        -- FanGraphs player ID
    key_npb             INTEGER,        -- Nippon Professional Baseball
    key_sr_nfl          TEXT,           -- Sports Reference NFL ID
    key_sr_nba          TEXT,           -- Sports Reference NBA ID
    key_sr_nhl          TEXT,           -- Sports Reference NHL ID
    key_findagrave      BIGINT,         -- Find A Grave memorial ID

    -- -------------------------------------------------------------------------
    -- Career dates
    -- -------------------------------------------------------------------------
    mlb_played_first    SMALLINT,       -- First year in MLB
    mlb_played_last     SMALLINT,       -- Last year in MLB

    -- -------------------------------------------------------------------------
    -- Audit
    -- -------------------------------------------------------------------------
    _ingested_at        TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_file        TEXT
);

COMMENT ON TABLE raw.playerid_map IS
    'Cross-source player ID mapping from Chadwick Bureau via pybaseball playerid_lookup(). '
    'Links MLBAM (Statcast), Retrosheet, Baseball Reference, FanGraphs, and Lahman IDs. '
    'Source: https://github.com/chadwickbureau/register';
