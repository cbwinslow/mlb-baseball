-- =============================================================================
-- Raw Retrosheet Play-by-Play Events Table
-- Source: Retrosheet (retrosheet.org)
-- Docs:   https://www.retrosheet.org/eventfile.htm
-- Notes:  This table stores the parsed output from Retrosheet .EVA/.EVN event
--         files after processing through BEVENT or a custom parser. Each row
--         represents one play/event from a game. All fields from the Retrosheet
--         event file specification are retained.
-- =============================================================================

CREATE TABLE IF NOT EXISTS raw.retrosheet_events (
    -- -------------------------------------------------------------------------
    -- Game identification
    -- -------------------------------------------------------------------------
    game_id                     TEXT NOT NULL,      -- 12-char game ID (e.g. ATL198304080)
    game_date                   DATE,               -- Date of game
    game_number                 SMALLINT,           -- 0=single, 1=first, 2=second game of DH
    home_team                   CHAR(3),            -- Retrosheet 3-char home team code
    vis_team                    CHAR(3),            -- Retrosheet 3-char visiting team code

    -- -------------------------------------------------------------------------
    -- Play identification
    -- -------------------------------------------------------------------------
    inning                      SMALLINT,           -- Inning number
    batting_team                SMALLINT,           -- 0=visitor, 1=home
    outs                        SMALLINT,           -- Outs at start of play (0-2)
    balls                       SMALLINT,           -- Balls in count when play occurred
    strikes                     SMALLINT,           -- Strikes in count when play occurred
    pitch_sequence              TEXT,               -- All pitches to batter (see Retrosheet pitch codes)
    batter_id                   TEXT,               -- Retrosheet player ID for batter
    pitcher_id                  TEXT,               -- Retrosheet player ID for pitcher

    -- -------------------------------------------------------------------------
    -- Base situation (pre-play)
    -- -------------------------------------------------------------------------
    runner_on_1b_id             TEXT,               -- Player ID of runner on 1B (NULL if empty)
    runner_on_2b_id             TEXT,               -- Player ID of runner on 2B (NULL if empty)
    runner_on_3b_id             TEXT,               -- Player ID of runner on 3B (NULL if empty)

    -- -------------------------------------------------------------------------
    -- The raw play event string
    -- -------------------------------------------------------------------------
    event_text                  TEXT,               -- Raw Retrosheet event string (e.g. S9/L9S.2-H;1-3)
    event_type                  SMALLINT,           -- Numeric event type code from BEVENT

    -- -------------------------------------------------------------------------
    -- Parsed event components
    -- -------------------------------------------------------------------------
    batted_ball_type            TEXT,               -- G=ground, F=fly, L=line drive, P=pop
    bunt_flag                   BOOLEAN,            -- True if bunt
    foul_flag                   BOOLEAN,            -- True if foul
    hit_value                   SMALLINT,           -- 0=out, 1=single, 2=double, 3=triple, 4=HR
    sacrifice_hit_flag          BOOLEAN,            -- Sacrifice hit/bunt
    sacrifice_fly_flag          BOOLEAN,            -- Sacrifice fly
    dp_flag                     BOOLEAN,            -- Double play
    gdp_flag                    BOOLEAN,            -- Grounded into double play
    tp_flag                     BOOLEAN,            -- Triple play
    wp_flag                     BOOLEAN,            -- Wild pitch
    pb_flag                     BOOLEAN,            -- Passed ball
    ab_flag                     BOOLEAN,            -- At bat
    hit_flag                    BOOLEAN,            -- Hit
    rbi_on_play                 SMALLINT,           -- RBIs credited on this play
    error_flag                  BOOLEAN,            -- Error occurred
    fielded_by                  SMALLINT,           -- Primary fielder (1-9)

    -- -------------------------------------------------------------------------
    -- Runner advances (post-play destination)
    -- -------------------------------------------------------------------------
    batter_dest                 SMALLINT,           -- Batter destination base (0=out, 1-4=bases)
    runner_on_1b_dest           SMALLINT,           -- Runner from 1B destination (0=out, 1-4)
    runner_on_2b_dest           SMALLINT,           -- Runner from 2B destination (0=out, 1-4)
    runner_on_3b_dest           SMALLINT,           -- Runner from 3B destination (0=out, 1-4)

    -- -------------------------------------------------------------------------
    -- Fielding credits (putout/assist positions)
    -- -------------------------------------------------------------------------
    putout_1                    SMALLINT,           -- First putout position
    putout_2                    SMALLINT,           -- Second putout position
    putout_3                    SMALLINT,           -- Third putout position
    assist_1                    SMALLINT,
    assist_2                    SMALLINT,
    assist_3                    SMALLINT,
    assist_4                    SMALLINT,
    assist_5                    SMALLINT,
    error_pos_1                 SMALLINT,           -- First error position
    error_pos_2                 SMALLINT,
    error_pos_3                 SMALLINT,

    -- -------------------------------------------------------------------------
    -- Stolen base / caught stealing
    -- -------------------------------------------------------------------------
    sb_2_flag                   BOOLEAN,            -- Stolen base of 2nd
    sb_3_flag                   BOOLEAN,            -- Stolen base of 3rd
    sb_h_flag                   BOOLEAN,            -- Stolen base of home
    cs_2_flag                   BOOLEAN,            -- Caught stealing 2nd
    cs_3_flag                   BOOLEAN,            -- Caught stealing 3rd
    cs_h_flag                   BOOLEAN,            -- Caught stealing home
    po_1_flag                   BOOLEAN,            -- Pickoff at 1st
    po_2_flag                   BOOLEAN,            -- Pickoff at 2nd
    po_3_flag                   BOOLEAN,            -- Pickoff at 3rd

    -- -------------------------------------------------------------------------
    -- Score (post-play)
    -- -------------------------------------------------------------------------
    visitor_score               SMALLINT,
    home_score                  SMALLINT,

    -- -------------------------------------------------------------------------
    -- Adjustments
    -- -------------------------------------------------------------------------
    batter_hand_adj             CHAR(1),            -- badj: actual hand batter used (L/R)
    pitcher_hand_adj            CHAR(1),            -- padj: actual hand pitcher used (L/R)
    pinch_runner_on_1b_id       TEXT,               -- radj: extra-inning runner placed on 2B+

    -- -------------------------------------------------------------------------
    -- Comments / uncertainty
    -- -------------------------------------------------------------------------
    uncertain_play_flag         BOOLEAN,            -- Play ends with '#' uncertainty marker
    comment_text                TEXT,               -- Associated com record, if any

    -- -------------------------------------------------------------------------
    -- Audit columns
    -- -------------------------------------------------------------------------
    _ingested_at                TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    _source_file                TEXT                -- Source .EVA/.EVN filename
);

COMMENT ON TABLE raw.retrosheet_events IS
    'Raw Retrosheet play-by-play events parsed from .EVA/.EVN files. '
    'One row per play/event. Source: https://www.retrosheet.org/eventfile.htm';
