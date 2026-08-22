-- Builds the empirical 24 base-out run expectancy table (gold.run_expectancy_24)
-- from raw.retrosheet_event for all seasons.

WITH event_half_inning AS (
    SELECT
        re._season::integer AS season,
        re.game_id,
        re.inn_ct,
        re.bat_home_id,
        re.event_id,
        re.outs_ct::smallint AS outs_before,
        (
            (CASE WHEN re.base1_run_id IS NOT NULL AND re.base1_run_id != '' THEN '1' ELSE '0' END)
            || (CASE WHEN re.base2_run_id IS NOT NULL AND re.base2_run_id != '' THEN '1' ELSE '0' END)
            || (CASE WHEN re.base3_run_id IS NOT NULL AND re.base3_run_id != '' THEN '1' ELSE '0' END)
        ) AS base_state,
        re.event_runs_ct::integer AS event_runs,
        SUM(re.event_runs_ct::integer) OVER (
            PARTITION BY re.game_id, re.inn_ct, re.bat_home_id
            ORDER BY re.event_id
            ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING
        ) AS runs_rest_of_inning
    FROM raw.retrosheet_event re
    WHERE re.outs_ct::integer BETWEEN 0 AND 2
),

matrix_agg AS (
    SELECT
        season,
        outs_before,
        base_state,
        ROUND(AVG(runs_rest_of_inning)::numeric, 4) AS runs_rest_of_inning,
        COUNT(*)::integer AS sample_size
    FROM event_half_inning
    WHERE base_state IN ('000', '100', '020', '003', '120', '103', '023', '123')
    GROUP BY season, outs_before, base_state
)

INSERT INTO gold.run_expectancy_24 (
    season,
    outs_before,
    base_state,
    runs_rest_of_inning,
    sample_size,
    _updated_at
)
SELECT
    season,
    outs_before,
    base_state,
    runs_rest_of_inning,
    sample_size,
    clock_timestamp()
FROM matrix_agg
ON CONFLICT (season, outs_before, base_state)
DO UPDATE SET
    runs_rest_of_inning = EXCLUDED.runs_rest_of_inning,
    sample_size = EXCLUDED.sample_size,
    _updated_at = EXCLUDED._updated_at;
