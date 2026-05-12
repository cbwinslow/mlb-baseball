-- =============================================================
-- 028_raw_retrosheet_legacy.sql
-- RAW Retrosheet data tables - official schema as published by
-- Retrosheet / py-retrosheet (wellsoliver/py-retrosheet)
-- Source: https://github.com/wellsoliver/py-retrosheet
-- Schema: raw
-- Tables: raw.retro_events, raw.retro_games, raw.retro_rosters,
--         raw.retro_teams, raw.retro_parkcodes,
--         raw.retro_lkup_* (lookup tables)
-- NOTE:   These tables preserve EVERY field exactly as Retrosheet
--         provides it.  Build your models on top of these.
-- =============================================================

-- -----------------------------------------------------------
-- raw.retro_events  (BEVENT output - play-by-play, 96+ fields)
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw.retro_events (
    game_id                   TEXT         NOT NULL,
    away_team_id              TEXT,
    inn_ct                    INTEGER,
    bat_home_id               TEXT,
    outs_ct                   INTEGER,
    balls_ct                  INTEGER,
    strikes_ct                INTEGER,
    pitch_seq_tx              TEXT,
    away_score_ct             INTEGER,
    home_score_ct             INTEGER,
    bat_id                    TEXT,
    bat_hand_cd               TEXT,
    resp_bat_id               TEXT,
    resp_bat_hand_cd          TEXT,
    pit_id                    TEXT,
    pit_hand_cd               TEXT,
    resp_pit_id               TEXT,
    resp_pit_hand_cd          TEXT,
    pos2_fld_id               TEXT,
    pos3_fld_id               TEXT,
    pos4_fld_id               TEXT,
    pos5_fld_id               TEXT,
    pos6_fld_id               TEXT,
    pos7_fld_id               TEXT,
    pos8_fld_id               TEXT,
    pos9_fld_id               TEXT,
    base1_run_id              TEXT,
    base2_run_id              TEXT,
    base3_run_id              TEXT,
    event_tx                  TEXT,
    leadoff_fl                TEXT,
    ph_fl                     TEXT,
    bat_fld_cd                TEXT,
    bat_lineup_id             TEXT,
    event_cd                  TEXT,
    bat_event_fl              TEXT,
    ab_fl                     TEXT,
    h_cd                      TEXT,
    sh_fl                     TEXT,
    sf_fl                     TEXT,
    event_outs_ct             INTEGER,
    dp_fl                     TEXT,
    tp_fl                     TEXT,
    rbi_ct                    INTEGER,
    wp_fl                     TEXT,
    pb_fl                     TEXT,
    fld_cd                    TEXT,
    battedball_cd             TEXT,
    bunt_fl                   TEXT,
    foul_fl                   TEXT,
    battedball_loc_tx         TEXT,
    err_ct                    INTEGER,
    err1_fld_cd               TEXT,
    err1_cd                   TEXT,
    err2_fld_cd               TEXT,
    err2_cd                   TEXT,
    err3_fld_cd               TEXT,
    err3_cd                   TEXT,
    bat_dest_id               TEXT,
    run1_dest_id              TEXT,
    run2_dest_id              TEXT,
    run3_dest_id              TEXT,
    bat_play_tx               TEXT,
    run1_play_tx              TEXT,
    run2_play_tx              TEXT,
    run3_play_tx              TEXT,
    run1_sb_fl                TEXT,
    run2_sb_fl                TEXT,
    run3_sb_fl                TEXT,
    run1_cs_fl                TEXT,
    run2_cs_fl                TEXT,
    run3_cs_fl                TEXT,
    run1_pk_fl                TEXT,
    run2_pk_fl                TEXT,
    run3_pk_fl                TEXT,
    run1_resp_pit_id          TEXT,
    run2_resp_pit_id          TEXT,
    run3_resp_pit_id          TEXT,
    game_new_fl               TEXT,
    game_end_fl               TEXT,
    pr_run1_fl                TEXT,
    pr_run2_fl                TEXT,
    pr_run3_fl                TEXT,
    removed_for_pr_run1_id    TEXT,
    removed_for_pr_run2_id    TEXT,
    removed_for_pr_run3_id    TEXT,
    removed_for_ph_bat_id     TEXT,
    removed_for_ph_bat_fld_cd TEXT,
    po1_fld_cd                TEXT,
    po2_fld_cd                TEXT,
    po3_fld_cd                TEXT,
    ass1_fld_cd               TEXT,
    ass2_fld_cd               TEXT,
    ass3_fld_cd               TEXT,
    ass4_fld_cd               TEXT,
    ass5_fld_cd               TEXT,
    event_id                  TEXT,
    -- extended fields
    home_team_id              TEXT,
    bat_team_id               TEXT,
    fld_team_id               TEXT,
    bat_last_id               TEXT,
    inn_new_fl                TEXT,
    inn_end_fl                TEXT,
    start_bat_score_ct        INTEGER,
    start_fld_score_ct        INTEGER,
    inn_runs_ct               INTEGER,
    game_pa_ct                INTEGER,
    inn_pa_ct                 INTEGER,
    pa_new_fl                 TEXT,
    pa_trunc_fl               TEXT,
    start_bases_cd            TEXT,
    end_bases_cd              TEXT,
    bat_start_fl              TEXT,
    resp_bat_start_fl         TEXT,
    bat_on_deck_id            TEXT,
    bat_in_hold_id            TEXT,
    pit_start_fl              TEXT,
    resp_pit_start_fl         TEXT,
    run1_fld_cd               TEXT,
    run1_lineup_cd            TEXT,
    run1_origin_event_id      TEXT,
    run2_fld_cd               TEXT,
    run2_lineup_cd            TEXT,
    run2_origin_event_id      TEXT,
    run3_fld_cd               TEXT,
    run3_lineup_cd            TEXT,
    run3_origin_event_id      TEXT,
    run1_resp_cat_id          TEXT,
    run2_resp_cat_id          TEXT,
    run3_resp_cat_id          TEXT,
    pa_ball_ct                INTEGER,
    pa_called_ball_ct         INTEGER DEFAULT 0,
    pa_intent_ball_ct         INTEGER,
    pa_pitchout_ball_ct       INTEGER,
    pa_hitbatter_ball_ct      INTEGER,
    pa_other_ball_ct          INTEGER,
    pa_strike_ct              INTEGER,
    pa_called_strike_ct       INTEGER,
    pa_swingmiss_strike_ct    INTEGER,
    pa_foul_strike_ct         INTEGER,
    pa_inplay_strike_ct       INTEGER,
    pa_other_strike_ct        INTEGER,
    event_runs_ct             INTEGER,
    fld_id                    TEXT,
    base2_force_fl            TEXT,
    base3_force_fl            TEXT,
    base4_force_fl            TEXT,
    bat_safe_err_fl           TEXT,
    bat_fate_id               TEXT,
    run1_fate_id              TEXT,
    run2_fate_id              TEXT,
    run3_fate_id              TEXT,
    fate_runs_ct              INTEGER,
    ass6_fld_cd               TEXT,
    ass7_fld_cd               TEXT,
    ass8_fld_cd               TEXT,
    ass9_fld_cd               TEXT,
    ass10_fld_cd              TEXT,
    unknown_out_exc_fl        TEXT,
    uncertain_play_exc_fl     TEXT,
    -- ingestion metadata
    source_file               TEXT,
    loaded_at                 TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (game_id, event_id)
);

CREATE INDEX IF NOT EXISTS ix_retro_events_game_id    ON raw.retro_events (game_id);
CREATE INDEX IF NOT EXISTS ix_retro_events_bat_id     ON raw.retro_events (bat_id);
CREATE INDEX IF NOT EXISTS ix_retro_events_pit_id     ON raw.retro_events (pit_id);
CREATE INDEX IF NOT EXISTS ix_retro_events_away_team  ON raw.retro_events (away_team_id);
CREATE INDEX IF NOT EXISTS ix_retro_events_home_team  ON raw.retro_events (home_team_id);

-- -----------------------------------------------------------
-- raw.retro_games  (BGAME output - one row per game)
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw.retro_games (
    game_id                   TEXT         NOT NULL PRIMARY KEY,
    game_dt                   INTEGER,
    game_ct                   INTEGER,
    game_dy                   TEXT,
    start_game_tm             INTEGER,
    dh_fl                     TEXT,
    daynight_park_cd          TEXT,
    away_team_id              TEXT,
    home_team_id              TEXT,
    park_id                   TEXT,
    away_start_pit_id         TEXT,
    home_start_pit_id         TEXT,
    base4_ump_id              TEXT,
    base1_ump_id              TEXT,
    base2_ump_id              TEXT,
    base3_ump_id              TEXT,
    lf_ump_id                 TEXT,
    rf_ump_id                 TEXT,
    attend_park_ct            INTEGER,
    scorer_record_id          TEXT,
    translator_record_id      TEXT,
    inputter_record_id        TEXT,
    input_record_ts           TEXT,
    edit_record_ts            TEXT,
    method_record_cd          TEXT,
    pitches_record_cd         TEXT,
    temp_park_ct              INTEGER,
    wind_direction_park_cd    INTEGER,
    wind_speed_park_ct        INTEGER,
    field_park_cd             INTEGER,
    precip_park_cd            INTEGER,
    sky_park_cd               INTEGER,
    minutes_game_ct           INTEGER,
    inn_ct                    INTEGER,
    away_score_ct             INTEGER,
    home_score_ct             INTEGER,
    away_hits_ct              INTEGER,
    home_hits_ct              INTEGER,
    away_err_ct               INTEGER,
    home_err_ct               INTEGER,
    away_lob_ct               INTEGER,
    home_lob_ct               INTEGER,
    win_pit_id                TEXT,
    lose_pit_id               TEXT,
    save_pit_id               TEXT,
    gwrbi_bat_id              TEXT,
    away_lineup1_bat_id       TEXT,
    away_lineup1_fld_cd       INTEGER,
    away_lineup2_bat_id       TEXT,
    away_lineup2_fld_cd       INTEGER,
    away_lineup3_bat_id       TEXT,
    away_lineup3_fld_cd       INTEGER,
    away_lineup4_bat_id       TEXT,
    away_lineup4_fld_cd       INTEGER,
    away_lineup5_bat_id       TEXT,
    away_lineup5_fld_cd       INTEGER,
    away_lineup6_bat_id       TEXT,
    away_lineup6_fld_cd       INTEGER,
    away_lineup7_bat_id       TEXT,
    away_lineup7_fld_cd       INTEGER,
    away_lineup8_bat_id       TEXT,
    away_lineup8_fld_cd       INTEGER,
    away_lineup9_bat_id       TEXT,
    away_lineup9_fld_cd       INTEGER,
    home_lineup1_bat_id       TEXT,
    home_lineup1_fld_cd       INTEGER,
    home_lineup2_bat_id       TEXT,
    home_lineup2_fld_cd       INTEGER,
    home_lineup3_bat_id       TEXT,
    home_lineup3_fld_cd       INTEGER,
    home_lineup4_bat_id       TEXT,
    home_lineup4_fld_cd       INTEGER,
    home_lineup5_bat_id       TEXT,
    home_lineup5_fld_cd       INTEGER,
    home_lineup6_bat_id       TEXT,
    home_lineup6_fld_cd       INTEGER,
    home_lineup7_bat_id       TEXT,
    home_lineup7_fld_cd       INTEGER,
    home_lineup8_bat_id       TEXT,
    home_lineup8_fld_cd       INTEGER,
    home_lineup9_bat_id       TEXT,
    home_lineup9_fld_cd       INTEGER,
    away_finish_pit_id        TEXT,
    home_finish_pit_id        TEXT,
    -- ingestion metadata
    source_file               TEXT,
    loaded_at                 TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_retro_games_away_team ON raw.retro_games (away_team_id);
CREATE INDEX IF NOT EXISTS ix_retro_games_home_team ON raw.retro_games (home_team_id);
CREATE INDEX IF NOT EXISTS ix_retro_games_game_dt   ON raw.retro_games (game_dt);

-- -----------------------------------------------------------
-- raw.retro_rosters  (yearly team roster files)
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw.retro_rosters (
    year                      INTEGER      NOT NULL,
    player_id                 TEXT         NOT NULL,
    last_name_tx              TEXT,
    first_name_tx             TEXT,
    bat_hand_cd               TEXT,
    pit_hand_cd               TEXT,
    team_tx                   TEXT         NOT NULL,
    pos_tx                    TEXT,
    -- ingestion metadata
    source_file               TEXT,
    loaded_at                 TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (year, player_id, team_tx)
);

CREATE INDEX IF NOT EXISTS ix_retro_rosters_player ON raw.retro_rosters (player_id);
CREATE INDEX IF NOT EXISTS ix_retro_rosters_team   ON raw.retro_rosters (team_tx, year);

-- -----------------------------------------------------------
-- raw.retro_teams  (team master)
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw.retro_teams (
    team_id                   TEXT         NOT NULL PRIMARY KEY,
    lg_id                     TEXT,
    loc_team_tx               TEXT,
    name_team_tx              TEXT,
    loaded_at                 TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- -----------------------------------------------------------
-- raw.retro_parkcodes  (ballpark master)
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw.retro_parkcodes (
    park_id                   TEXT         NOT NULL PRIMARY KEY,
    name                      TEXT,
    aka                       TEXT,
    city                      TEXT,
    state                     TEXT,
    start                     TEXT,
    "end"                     TEXT,
    league                    TEXT,
    notes                     TEXT,
    loaded_at                 TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- -----------------------------------------------------------
-- raw.retro_lkup_* (lookup / code tables)
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw.retro_lkup_bases        (value_cd INTEGER, shortname_tx TEXT, longname_tx TEXT, description_tx TEXT);
CREATE TABLE IF NOT EXISTS raw.retro_lkup_battedball   (value_cd TEXT,    shortname_tx TEXT, longname_tx TEXT, description_tx TEXT);
CREATE TABLE IF NOT EXISTS raw.retro_lkup_event        (value_cd INTEGER, shortname_tx TEXT, longname_tx TEXT, description_tx TEXT);
CREATE TABLE IF NOT EXISTS raw.retro_lkup_fld          (value_cd INTEGER, shortname_tx TEXT, longname_tx TEXT, description_tx TEXT);
CREATE TABLE IF NOT EXISTS raw.retro_lkup_h            (value_cd INTEGER, shortname_tx TEXT, longname_tx TEXT, description_tx TEXT);
CREATE TABLE IF NOT EXISTS raw.retro_lkup_hand         (value_cd TEXT,    shortname_tx TEXT, longname_tx TEXT, description_tx TEXT);
CREATE TABLE IF NOT EXISTS raw.retro_lkup_park_daynight(value_cd TEXT,    shortname_tx TEXT, longname_tx TEXT, description_tx TEXT);
CREATE TABLE IF NOT EXISTS raw.retro_lkup_park_field   (value_cd INTEGER, shortname_tx TEXT, longname_tx TEXT, description_tx TEXT);
CREATE TABLE IF NOT EXISTS raw.retro_lkup_park_precip  (value_cd INTEGER, shortname_tx TEXT, longname_tx TEXT, description_tx TEXT);
CREATE TABLE IF NOT EXISTS raw.retro_lkup_park_sky     (value_cd INTEGER, shortname_tx TEXT, longname_tx TEXT, description_tx TEXT);
CREATE TABLE IF NOT EXISTS raw.retro_lkup_park_wind    (value_cd INTEGER, shortname_tx TEXT, longname_tx TEXT, description_tx TEXT);
CREATE TABLE IF NOT EXISTS raw.retro_lkup_rec_method   (value_cd INTEGER, shortname_tx TEXT, longname_tx TEXT, description_tx TEXT);
CREATE TABLE IF NOT EXISTS raw.retro_lkup_rec_pitches  (value_cd INTEGER, shortname_tx TEXT, longname_tx TEXT, description_tx TEXT);
CREATE TABLE IF NOT EXISTS raw.retro_lkup_id_base      (value_cd INTEGER, shortname_tx TEXT, longname_tx TEXT, description_tx TEXT);
CREATE TABLE IF NOT EXISTS raw.retro_lkup_id_home      (value_cd INTEGER, shortname_tx TEXT, longname_tx TEXT, description_tx TEXT);
CREATE TABLE IF NOT EXISTS raw.retro_lkup_id_last      (value_cd INTEGER, shortname_tx TEXT, longname_tx TEXT, description_tx TEXT);
