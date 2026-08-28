-- Staging table for leverage_index.compute()'s chunked, per-season build
-- (mlb_baseball/sql/leverage_index_season_partial.sql /
-- leverage_index_matrix_finalize.sql). Replaces a single, unobservable
-- query over the full ~16M-row raw.retrosheet_event table (confirmed
-- directly: ran 4.5+ hours against real production with no way to tell
-- whether it was making real progress) with ~123 small per-season
-- queries whose progress is directly visible from Python between calls.
-- Real per-season SUM(swing)/COUNT(*) land here; leverage_index_matrix_
-- finalize.sql pools them into the real gold.leverage_index afterward --
-- mathematically identical to a single-pass AVG, just chunked.

CREATE TABLE IF NOT EXISTS gold.leverage_index_staging (
    season smallint NOT NULL,
    inning_bucket smallint NOT NULL CHECK (inning_bucket >= 1 AND inning_bucket <= 9),
    is_bottom boolean NOT NULL,
    outs_before smallint NOT NULL CHECK (outs_before >= 0 AND outs_before <= 2),
    base_state varchar(3) NOT NULL
        CHECK (base_state IN ('000', '100', '010', '001', '110', '101', '011', '111')),
    margin_bucket smallint NOT NULL CHECK (margin_bucket >= -8 AND margin_bucket <= 8),
    swing_sum numeric NOT NULL,
    swing_count integer NOT NULL,
    PRIMARY KEY (season, inning_bucket, is_bottom, outs_before, base_state, margin_bucket)
);
