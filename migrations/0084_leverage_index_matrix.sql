-- Empirical Leverage Index table (Plan 06, ADR-262). Pooled across all
-- seasons (unlike gold.win_expectancy, which is per-season) -- leverage's
-- inning/outs/base/margin shape is stable across eras even though raw
-- run-scoring rates aren't, and pooling gives far better sample sizes for
-- rare extreme states. See mlb_baseball/sql/leverage_index_matrix_build.sql
-- for the full derivation.

CREATE TABLE IF NOT EXISTS gold.leverage_index (
    inning_bucket smallint NOT NULL CHECK (inning_bucket BETWEEN 1 AND 9),
    is_bottom boolean NOT NULL,
    outs_before smallint NOT NULL CHECK (outs_before BETWEEN 0 AND 2),
    base_state varchar(3) NOT NULL CHECK (base_state IN ('000', '100', '010', '001', '110', '101', '011', '111')),
    margin_bucket smallint NOT NULL CHECK (margin_bucket BETWEEN -8 AND 8),
    leverage_index numeric(8, 4) NOT NULL CHECK (leverage_index >= 0),
    sample_size integer NOT NULL,
    _updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (inning_bucket, is_bottom, outs_before, base_state, margin_bucket)
);
