-- Phase 2 kickoff (ADR-032): gold.game_feature, one row per core.game, holding
-- only what was actually knowable before first pitch. Every column here is
-- either sourced from core.game's own pre-game fields, or must be computed
-- from games/plays strictly before the target game's date -- never from
-- core.standing or core.player_war's current-season aggregates (see ADR-032
-- for why those two are real leakage traps, found inspecting the schema
-- directly before writing this).
--
-- No population logic yet -- this migration is schema only. The build job
-- (a new module, not yet written) is separate, deliberate follow-up work.

CREATE TABLE gold.game_feature (
    game_id bigint PRIMARY KEY REFERENCES core.game (id),
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

CREATE INDEX game_feature_season_idx ON gold.game_feature (season);
