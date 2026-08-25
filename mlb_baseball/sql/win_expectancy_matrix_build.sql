-- Builds the empirical win-expectancy table (gold.win_expectancy) from
-- raw.retrosheet_event + core.game's real final scores, for all seasons.
-- Same methodology as run_expectancy_matrix_build.sql (empirical average
-- outcome given a real, observed state), with a binary "home team won"
-- outcome instead of "runs scored the rest of the inning" and three extra
-- state dimensions (inning, half, score margin) since win probability,
-- unlike run expectancy, genuinely depends on the score and how much of
-- the game remains, not just the base/out state.

WITH game_winner AS (
    SELECT g.retro_game_id, (g.home_score > g.away_score) AS home_won
    FROM core.game g
    WHERE g.game_type = 'regular' AND g.home_score IS NOT NULL AND g.away_score IS NOT NULL
),

event_state AS (
    SELECT
        re._season::integer AS season,
        re.game_id,
        LEAST(re.inn_ct::integer, 9) AS inning_bucket,
        (re.bat_home_id = '1') AS is_bottom,
        re.outs_ct::smallint AS outs_before,
        (
            (CASE WHEN re.base1_run_id IS NOT NULL AND re.base1_run_id != '' THEN '1' ELSE '0' END)
            || (CASE WHEN re.base2_run_id IS NOT NULL AND re.base2_run_id != '' THEN '1' ELSE '0' END)
            || (CASE WHEN re.base3_run_id IS NOT NULL AND re.base3_run_id != '' THEN '1' ELSE '0' END)
        ) AS base_state,
        -- Home-minus-away score margin entering this play, capped to +/-8
        -- (beyond that the game is effectively decided either way -- real
        -- sample sizes out there are thin and WE is already near 0/1).
        GREATEST(-8, LEAST(8,
            CASE WHEN re.bat_home_id = '1'
                THEN re.start_bat_score_ct::integer - re.start_fld_score_ct::integer
                ELSE re.start_fld_score_ct::integer - re.start_bat_score_ct::integer
            END
        )) AS margin_bucket,
        gw.home_won
    FROM raw.retrosheet_event re
    JOIN raw.retrosheet_gameinfo gi ON gi.gid = re.game_id AND lower(gi.gametype) = 'regular'
    JOIN game_winner gw ON gw.retro_game_id = re.game_id
    WHERE re.outs_ct::integer BETWEEN 0 AND 2
),

matrix_agg AS (
    SELECT
        season, inning_bucket, is_bottom, outs_before, base_state, margin_bucket,
        ROUND(AVG(CASE WHEN home_won THEN 1.0 ELSE 0.0 END)::numeric, 4) AS home_win_pct,
        COUNT(*)::integer AS sample_size
    FROM event_state
    WHERE base_state IN ('000', '100', '010', '001', '110', '101', '011', '111')
    GROUP BY season, inning_bucket, is_bottom, outs_before, base_state, margin_bucket
)

INSERT INTO gold.win_expectancy (
    season, inning_bucket, is_bottom, outs_before, base_state, margin_bucket,
    home_win_pct, sample_size, _updated_at
)
SELECT
    season, inning_bucket, is_bottom, outs_before, base_state, margin_bucket,
    home_win_pct, sample_size, clock_timestamp()
FROM matrix_agg
ON CONFLICT (season, inning_bucket, is_bottom, outs_before, base_state, margin_bucket)
DO UPDATE SET
    home_win_pct = EXCLUDED.home_win_pct,
    sample_size = EXCLUDED.sample_size,
    _updated_at = EXCLUDED._updated_at;
