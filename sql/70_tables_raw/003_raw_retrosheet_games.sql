-- =============================================================================
-- Raw Retrosheet Game Info Table
-- Source: Retrosheet (retrosheet.org)
-- Docs:   https://www.retrosheet.org/eventfile.htm (info records)
-- Notes:  Each row represents one game. All `info` record fields from the
--         Retrosheet event file are captured here, including administrative
--         fields and weather/conditions data.
-- =============================================================================

CREATE TABLE IF NOT EXISTS raw.retrosheet_games (
    -- -------------------------------------------------------------------------
    -- Primary identifier
    -- -------------------------------------------------------------------------
    game_id                     TEXT NOT NULL,      -- 12-char game ID e.g. ATL198304080
    game_date                   DATE,               -- From info,date (yyyy/mm/dd)
    game_number                 SMALLINT,           -- 0=single, 1=DH game 1, 2=DH game 2

    -- -------------------------------------------------------------------------
    -- Teams
    -- -------------------------------------------------------------------------
    home_team                   CHAR(3),            -- info,hometeam
    vis_team                    CHAR(3),            -- info,visteam

    -- -------------------------------------------------------------------------
    -- Game conditions
    -- -------------------------------------------------------------------------
    start_time                  TEXT,               -- info,starttime (e.g. 7:44PM)
    day_night                   TEXT,               -- info,daynight (day/night)
    innings_scheduled           SMALLINT,           -- info,innings (usually 9, sometimes 7)
    use_dh                      BOOLEAN,            -- info,usedh
    tiebreaker_base             SMALLINT,           -- info,tiebreaker (2020+ extra innings)
    home_team_bats_first        BOOLEAN,            -- info,htbf
    pitches_available           TEXT,               -- info,pitches (pitches/count/none)
    game_type                   TEXT,               -- info,gametype (regular/playoff/worldseries etc.)

    -- -------------------------------------------------------------------------
    -- Umpires
    -- -------------------------------------------------------------------------
    ump_home_id                 TEXT,               -- info,umphome
    ump_1b_id                   TEXT,               -- info,ump1b
    ump_2b_id                   TEXT,               -- info,ump2b
    ump_3b_id                   TEXT,               -- info,ump3b
    ump_lf_id                   TEXT,               -- info,umplf
    ump_rf_id                   TEXT,               -- info,umprf

    -- -------------------------------------------------------------------------
    -- Weather
    -- -------------------------------------------------------------------------
    field_cond                  TEXT,               -- info,fieldcond (dry/wet/soaked/unknown)
    precip                      TEXT,               -- info,precip (none/drizzle/rain/snow/unknown)
    sky                         TEXT,               -- info,sky (sunny/cloudy/night/dome/overcast)
    temp                        SMALLINT,           -- info,temp (Fahrenheit; 0 = unknown)
    wind_dir                    TEXT,               -- info,winddir
    wind_speed                  SMALLINT,           -- info,windspeed (-1 = unknown)

    -- -------------------------------------------------------------------------
    -- Game results
    -- -------------------------------------------------------------------------
    time_of_game_min            SMALLINT,           -- info,timeofgame (minutes)
    attendance                  INTEGER,            -- info,attendance
    site_id                     TEXT,               -- info,site (park code)
    winning_pitcher_id          TEXT,               -- info,wp
    losing_pitcher_id           TEXT,               -- info,lp
    save_pitcher_id             TEXT,               -- info,save (may be NULL)
    gwrbi_player_id             TEXT,               -- info,gwrbi (historical stat, may be NULL)
    official_scorer_id          TEXT,               -- info,oscorer

    -- -------------------------------------------------------------------------
    -- Administrative / data provenance
    -- -------------------------------------------------------------------------
    edit_time                   TEXT,               -- info,edittime
    how_scored                  TEXT,               -- info,howscored (park/tv/radio/unknown)
    input_program_version       TEXT,               -- info,inputprogvers
    inputter                    TEXT,               -- info,inputter
    input_time                  TEXT,               -- info,inputtime
    scorer                      TEXT,               -- info,scorer
    translator                  TEXT,               -- info,translator

    -- -------------------------------------------------------------------------
    -- Audit
    -- -------------------------------------------------------------------------
    _ingested_at                TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_file                TEXT
);

COMMENT ON TABLE raw.retrosheet_games IS
    'Raw Retrosheet game-level info records (one row per game). '
    'Source: https://www.retrosheet.org/eventfile.htm';
