-- Pools every season's real swing sums (built one season at a time by
-- leverage_index_season_partial.sql, into gold.leverage_index_staging)
-- into the final gold.leverage_index table. SUM/COUNT decomposes exactly
-- the same as computing AVG(swing) in one single-pass query would --
-- pooling across seasons here is mathematically identical to the original
-- single-query leverage_index_matrix_build.sql, just computed from
-- pre-aggregated per-season sums instead of the full 16M-row event stream
-- directly, since the per-season partials already did that heavy lifting.
-- See leverage_index_matrix_build.sql / leverage_index_season_partial.sql
-- for the full real-definition citation and swing-computation reasoning.

WITH global_avg AS (
    SELECT SUM(swing_sum) / SUM(swing_count) AS avg_swing FROM gold.leverage_index_staging
),

matrix_agg AS (
    SELECT
        s.inning_bucket, s.is_bottom, s.outs_before, s.base_state, s.margin_bucket,
        ROUND((SUM(s.swing_sum) / SUM(s.swing_count) / ga.avg_swing)::numeric, 4) AS leverage_index,
        SUM(s.swing_count)::integer AS sample_size
    FROM gold.leverage_index_staging s, global_avg ga
    GROUP BY s.inning_bucket, s.is_bottom, s.outs_before, s.base_state, s.margin_bucket, ga.avg_swing
)

INSERT INTO gold.leverage_index (
    inning_bucket, is_bottom, outs_before, base_state, margin_bucket,
    leverage_index, sample_size, _updated_at
)
SELECT
    inning_bucket, is_bottom, outs_before, base_state, margin_bucket,
    leverage_index, sample_size, clock_timestamp()
FROM matrix_agg
ON CONFLICT (inning_bucket, is_bottom, outs_before, base_state, margin_bucket)
DO UPDATE SET
    leverage_index = EXCLUDED.leverage_index,
    sample_size = EXCLUDED.sample_size,
    _updated_at = EXCLUDED._updated_at;
