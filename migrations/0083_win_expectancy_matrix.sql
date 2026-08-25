-- Empirical win-expectancy table (Plan 06, ADR-262). Backs a real
-- Leverage Index rebuild -- see docs/DECISIONS.md ADR-262 for why the
-- previous home_starter_avg_li/home_bullpen_avg_li columns (added by
-- migration 0068) were computed from a hand-typed, unvalidated table
-- instead of real data. This migration only adds the lookup table itself;
-- 0068's avg_li/re24 columns on gold.game_feature are reused, not
-- redefined.

CREATE TABLE IF NOT EXISTS gold.win_expectancy (
    season integer NOT NULL,
    inning_bucket smallint NOT NULL CHECK (inning_bucket BETWEEN 1 AND 9),
    is_bottom boolean NOT NULL,
    outs_before smallint NOT NULL CHECK (outs_before BETWEEN 0 AND 2),
    base_state varchar(3) NOT NULL CHECK (base_state IN ('000', '100', '010', '001', '110', '101', '011', '111')),
    margin_bucket smallint NOT NULL CHECK (margin_bucket BETWEEN -8 AND 8),
    home_win_pct numeric(6, 4) NOT NULL CHECK (home_win_pct BETWEEN 0 AND 1),
    sample_size integer NOT NULL,
    _updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (season, inning_bucket, is_bottom, outs_before, base_state, margin_bucket)
);
