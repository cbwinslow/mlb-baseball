-- =============================================================
-- 01_raw_mlbstatsapi.sql
-- RAW MLB Stats API data tables
-- Source: https://statsapi.mlb.com/api/v1/
--         MLB-StatsAPI Python client (toddrob99/MLB-StatsAPI)
-- Schema: raw
-- Tables: raw.mlb_schedule, raw.mlb_game, raw.mlb_player,
--         raw.mlb_team, raw.mlb_standings, raw.mlb_boxscore
-- NOTE:   All fields from the official MLB Stats API endpoints
--         are preserved here exactly as returned.
-- =============================================================

-- -----------------------------------------------------------
-- raw.mlb_schedule
-- /api/v1/schedule endpoint - one row per scheduled game
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw.mlb_schedule (
    game_pk                    BIGINT       NOT NULL PRIMARY KEY,
    game_guid                  TEXT,
    link                       TEXT,
    game_type                  TEXT,         -- R=Regular, S=Spring, P=Postseason, etc.
    season                     TEXT,
    game_date                  DATE,
    official_date              DATE,
    status_abstract_game_state TEXT,         -- Preview / Live / Final
    status_coded_game_state    TEXT,
    status_detailed_state      TEXT,
    status_status_code         TEXT,
    status_start_time_tbd      BOOLEAN,
    status_abstract_game_code  TEXT,
    teams_away_score           INTEGER,
    teams_away_is_winner       BOOLEAN,
    teams_away_split_squad     BOOLEAN,
    teams_away_series_number   INTEGER,
    teams_away_league_record_wins SMALLINT,
    teams_away_league_record_losses SMALLINT,
    teams_away_league_record_pct TEXT,
    teams_away_team_id         INTEGER,
    teams_away_team_name       TEXT,
    teams_away_team_link       TEXT,
    teams_home_score           INTEGER,
    teams_home_is_winner       BOOLEAN,
    teams_home_split_squad     BOOLEAN,
    teams_home_series_number   INTEGER,
    teams_home_league_record_wins SMALLINT,
    teams_home_league_record_losses SMALLINT,
    teams_home_league_record_pct TEXT,
    teams_home_team_id         INTEGER,
    teams_home_team_name       TEXT,
    teams_home_team_link       TEXT,
    venue_id                   INTEGER,
    venue_name                 TEXT,
    venue_link                 TEXT,
    content_link               TEXT,
    is_tie                     BOOLEAN,
    game_number                SMALLINT,
    public_facing              BOOLEAN,
    double_header              TEXT,         -- N / Y / S
    games_in_series            SMALLINT,
    series_game_number         SMALLINT,
    series_description         TEXT,
    record_source              TEXT,
    if_necessary               TEXT,
    if_necessary_description   TEXT,
    day_night                  TEXT,         -- day / night
    description                TEXT,
    scheduled_innings          SMALLINT,
    inning_break_length        INTEGER,
    reverse_home_away_status   BOOLEAN,
    innings_live               SMALLINT,
    innings_live_final         SMALLINT,
    -- ingestion metadata
    source_url                 TEXT,
    loaded_at                  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_mlb_schedule_date    ON raw.mlb_schedule (game_date);
CREATE INDEX IF NOT EXISTS ix_mlb_schedule_season  ON raw.mlb_schedule (season);
CREATE INDEX IF NOT EXISTS ix_mlb_schedule_away    ON raw.mlb_schedule (teams_away_team_id);
CREATE INDEX IF NOT EXISTS ix_mlb_schedule_home    ON raw.mlb_schedule (teams_home_team_id);

-- -----------------------------------------------------------
-- raw.mlb_game_linescore
-- /api/v1.1/game/{gamePk}/linescore - inning-by-inning scores
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw.mlb_game_linescore (
    game_pk                    BIGINT       NOT NULL,
    current_inning             SMALLINT,
    current_inning_ordinal     TEXT,
    inning_state               TEXT,
    inning_half                TEXT,
    is_top_inning              BOOLEAN,
    scheduled_innings          SMALLINT,
    innings_in_order           BOOLEAN,
    team_away_runs             INTEGER,
    team_away_hits             INTEGER,
    team_away_errors           INTEGER,
    team_away_left_on_base     INTEGER,
    team_home_runs             INTEGER,
    team_home_hits             INTEGER,
    team_home_errors           INTEGER,
    team_home_left_on_base     INTEGER,
    balls                      SMALLINT,
    strikes                    SMALLINT,
    outs                       SMALLINT,
    loaded_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (game_pk)
);

-- -----------------------------------------------------------
-- raw.mlb_player
-- /api/v1/people/{playerId} - player bio and attributes
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw.mlb_player (
    id                         INTEGER      NOT NULL PRIMARY KEY,
    full_name                  TEXT,
    link                       TEXT,
    first_name                 TEXT,
    last_name                  TEXT,
    primary_number             TEXT,        -- jersey number
    birth_date                 DATE,
    current_age                SMALLINT,
    birth_city                 TEXT,
    birth_state_province       TEXT,
    birth_country              TEXT,
    height                     TEXT,        -- e.g. "6' 2""
    weight                     INTEGER,
    active                     BOOLEAN,
    primary_position_code      TEXT,
    primary_position_name      TEXT,
    primary_position_type      TEXT,
    primary_position_abbreviation TEXT,
    use_name                   TEXT,
    use_last_name              TEXT,
    middle_name                TEXT,
    boxscore_name              TEXT,
    nick_name                  TEXT,
    gender                     TEXT,
    is_player                  BOOLEAN,
    is_verified                BOOLEAN,
    draft_year                 SMALLINT,
    mlb_debut_date             DATE,
    bat_side_code              TEXT,        -- L / R / S
    bat_side_description       TEXT,
    pitch_hand_code            TEXT,        -- L / R / S
    pitch_hand_description     TEXT,
    name_first_last            TEXT,
    name_slug                  TEXT,
    first_last_name            TEXT,
    last_first_name            TEXT,
    last_init_name             TEXT,
    init_last_name             TEXT,
    full_fml_name              TEXT,
    full_lfm_name              TEXT,
    strike_zone_top            NUMERIC(6,3),
    strike_zone_bottom         NUMERIC(6,3),
    -- ingestion metadata
    source_url                 TEXT,
    loaded_at                  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_mlb_player_last_name ON raw.mlb_player (last_name);
CREATE INDEX IF NOT EXISTS ix_mlb_player_active    ON raw.mlb_player (active);

-- -----------------------------------------------------------
-- raw.mlb_team
-- /api/v1/teams - team information
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw.mlb_team (
    id                         INTEGER      NOT NULL PRIMARY KEY,
    name                       TEXT,
    link                       TEXT,
    season                     SMALLINT,
    venue_id                   INTEGER,
    venue_name                 TEXT,
    venue_link                 TEXT,
    team_code                  TEXT,
    file_code                  TEXT,
    abbreviation               TEXT,
    team_name                  TEXT,
    location_name              TEXT,
    first_year_of_play         TEXT,
    league_id                  INTEGER,
    league_name                TEXT,
    league_link                TEXT,
    division_id                INTEGER,
    division_name              TEXT,
    division_link              TEXT,
    sport_id                   INTEGER,
    sport_link                 TEXT,
    sport_name                 TEXT,
    short_name                 TEXT,
    franchise_name             TEXT,
    club_name                  TEXT,
    all_star_status            TEXT,
    active                     BOOLEAN,
    -- ingestion metadata
    source_url                 TEXT,
    loaded_at                  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- -----------------------------------------------------------
-- raw.mlb_venue
-- /api/v1/venues - ballpark / venue information
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw.mlb_venue (
    id                         INTEGER      NOT NULL PRIMARY KEY,
    name                       TEXT,
    link                       TEXT,
    active                     BOOLEAN,
    season                     SMALLINT,
    location_address1          TEXT,
    location_city              TEXT,
    location_state             TEXT,
    location_state_abbrev      TEXT,
    location_postal_code       TEXT,
    location_country           TEXT,
    location_phone             TEXT,
    location_latitude          NUMERIC(10,6),
    location_longitude         NUMERIC(10,6),
    timezone_id                TEXT,
    timezone_offset            SMALLINT,
    timezone_tz                TEXT,
    field_center               INTEGER,     -- center field distance (ft)
    field_left                 INTEGER,
    field_right                INTEGER,
    field_roof_type            TEXT,
    field_turf_type            TEXT,
    capacity                   INTEGER,
    -- ingestion metadata
    source_url                 TEXT,
    loaded_at                  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- -----------------------------------------------------------
-- raw.mlb_standings
-- /api/v1/standings - division standings records
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw.mlb_standings (
    standings_id               BIGSERIAL    PRIMARY KEY,
    season                     TEXT         NOT NULL,
    standings_type             TEXT,        -- regularSeason / wildCard / etc.
    league_id                  INTEGER,
    division_id                INTEGER,
    division_name              TEXT,
    team_id                    INTEGER,
    team_name                  TEXT,
    division_rank              TEXT,
    league_rank                TEXT,
    sport_rank                 TEXT,
    games_back                 TEXT,
    wild_card_games_back       TEXT,
    league_games_back          TEXT,
    sport_games_back           TEXT,
    division_games_back        TEXT,
    wins                       SMALLINT,
    losses                     SMALLINT,
    pct                        TEXT,
    games_played               SMALLINT,
    runs_allowed               INTEGER,
    runs_scored                INTEGER,
    run_differential           INTEGER,
    home_wins                  SMALLINT,
    home_losses                SMALLINT,
    away_wins                  SMALLINT,
    away_losses                SMALLINT,
    last_ten_wins              SMALLINT,
    last_ten_losses            SMALLINT,
    extra_inning_wins          SMALLINT,
    extra_inning_losses        SMALLINT,
    one_run_wins               SMALLINT,
    one_run_losses             SMALLINT,
    day_wins                   SMALLINT,
    day_losses                 SMALLINT,
    night_wins                 SMALLINT,
    night_losses               SMALLINT,
    grass_wins                 SMALLINT,
    grass_losses               SMALLINT,
    turf_wins                  SMALLINT,
    turf_losses                SMALLINT,
    division_wins              SMALLINT,
    division_losses            SMALLINT,
    league_wins                SMALLINT,
    league_losses              SMALLINT,
    wild_card_rank             TEXT,
    clinched_wild_card         BOOLEAN,
    elimination_number         TEXT,
    wild_card_elimination_number TEXT,
    magic_number               TEXT,
    -- ingestion metadata
    source_url                 TEXT,
    loaded_at                  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_mlb_standings_season  ON raw.mlb_standings (season);
CREATE INDEX IF NOT EXISTS ix_mlb_standings_team    ON raw.mlb_standings (team_id, season);
CREATE INDEX IF NOT EXISTS ix_mlb_standings_div     ON raw.mlb_standings (division_id, season);

-- -----------------------------------------------------------
-- raw.mlb_roster
-- /api/v1/teams/{teamId}/roster - active roster
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw.mlb_roster (
    roster_id                  BIGSERIAL    PRIMARY KEY,
    team_id                    INTEGER      NOT NULL,
    season                     SMALLINT     NOT NULL,
    roster_type                TEXT,        -- active / fullRoster / 40Man / etc.
    player_id                  INTEGER      NOT NULL,
    player_full_name           TEXT,
    player_link                TEXT,
    jersey_number              TEXT,
    position_code              TEXT,
    position_name              TEXT,
    position_type              TEXT,
    position_abbreviation      TEXT,
    status_code                TEXT,
    status_description         TEXT,
    parent_team_id             INTEGER,
    -- ingestion metadata
    source_url                 TEXT,
    loaded_at                  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uidx_mlb_roster_team_player_season
    ON raw.mlb_roster (team_id, player_id, season, roster_type);
CREATE INDEX IF NOT EXISTS ix_mlb_roster_player ON raw.mlb_roster (player_id);
CREATE INDEX IF NOT EXISTS ix_mlb_roster_team   ON raw.mlb_roster (team_id, season);
