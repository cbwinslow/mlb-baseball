-- Broadens gold.game_feature to also cover upcoming (not-yet-played) games,
-- sourced directly from raw.mlb_schedule rather than core.game -- core.game
-- only ever holds *completed* games by design (conform.py's _build_games
-- explicitly excludes status IN ('Scheduled', 'Postponed', ...), correct
-- for Phase 1's historical-record scope). Without this, mlb predict has
-- nothing upcoming to ever generate a prediction for.
--
-- game_id can no longer be gold.game_feature's identity: an upcoming game
-- has no core.game row yet. mlb_game_pk (MLB's own numeric game ID --
-- raw.mlb_schedule.game_id, and the same value core.game.game_pk
-- eventually resolves to once the game is conformed) is the identity that
-- works both before and after a game lands in core.game. game_id stays as
-- a nullable, populated-when-known convenience column, not the anchor.
--
-- Both tables are fully rebuilt every run (mlb predict: TRUNCATE+rebuild
-- for game_feature, re-derived for prediction) -- drop and recreate rather
-- than ALTER, no data worth preserving across this shape change.

DROP TABLE gold.prediction;
DROP TABLE gold.game_feature;

CREATE TABLE gold.game_feature (
    id bigserial PRIMARY KEY,
    game_id bigint REFERENCES core.game (id),
    mlb_game_pk text,
    season integer NOT NULL,
    game_date date NOT NULL,
    home_team_id bigint REFERENCES core.team (id),
    away_team_id bigint REFERENCES core.team (id),

    -- Season-to-date record and run differential, computed from core.game
    -- rows strictly before game_date -- never from core.standing (no date
    -- history, see ADR-032).
    home_win_pct numeric,
    away_win_pct numeric,
    home_win_pct_10 numeric,
    away_win_pct_10 numeric,
    home_run_diff numeric,
    away_run_diff numeric,

    -- Classical baselines (ADR-032): Pythagorean expectation from the same
    -- season-to-date runs above, and Elo ratings updated incrementally
    -- game by game.
    home_pyth_wpct numeric,
    away_pyth_wpct numeric,
    home_elo numeric,
    away_elo numeric,

    -- Actual starters, derived from core.play's first row per half-inning
    -- (see ADR-032 for why this isn't leakage). ERA/rest computed only from
    -- that pitcher's starts strictly before game_date.
    home_starter_id bigint REFERENCES core.player (id),
    away_starter_id bigint REFERENCES core.player (id),
    home_starter_era numeric,
    away_starter_era numeric,
    home_starter_rest integer,
    away_starter_rest integer,

    -- Days since each team's prior game -- fatigue/back-to-back signal.
    home_rest integer,
    away_rest integer,

    -- Prior-season (lagged one full season) team WAR from core.player_war --
    -- current-season WAR is a leakage trap, see ADR-032. NULL for a team's
    -- first tracked season, not a bug.
    home_war_prior numeric,
    away_war_prior numeric,

    -- Venue/conditions. temp_f/wind/sky/precip are core.game's own actual
    -- observed values (fine for backtesting; a live-prediction build would
    -- need a forecast instead -- a known, separate future concern).
    venue_id bigint REFERENCES core.venue (id),
    day_night text,
    temp_f integer,
    wind_dir text,
    wind_speed_mph integer,
    sky text,
    precip text,

    -- Label -- never a feature. NULL until the game is final.
    home_win boolean,

    _built_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX game_feature_game_id_key ON gold.game_feature (game_id) WHERE game_id IS NOT NULL;
CREATE UNIQUE INDEX game_feature_mlb_game_pk_key ON gold.game_feature (mlb_game_pk) WHERE mlb_game_pk IS NOT NULL;
CREATE INDEX game_feature_season_idx ON gold.game_feature (season);

-- mlb_game_pk, not game_id: predict() only ever targets undecided games
-- (see log5.py), and every undecided game gold.game_feature builds a row
-- for came from raw.mlb_schedule and so always has mlb_game_pk populated --
-- game_id would be NULL for exactly the rows gold.prediction needs.
CREATE TABLE gold.prediction (
    mlb_game_pk text NOT NULL,
    model_version text NOT NULL,
    generated_at timestamptz NOT NULL DEFAULT now(),
    home_win_prob numeric NOT NULL,
    actual_home_win boolean,
    PRIMARY KEY (mlb_game_pk, model_version, generated_at)
);

CREATE INDEX prediction_game_idx ON gold.prediction (mlb_game_pk);
CREATE INDEX prediction_model_idx ON gold.prediction (model_version);
