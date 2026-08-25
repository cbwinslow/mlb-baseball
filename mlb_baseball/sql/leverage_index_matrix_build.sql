-- Builds the empirical Leverage Index table (gold.leverage_index) from real
-- Retrosheet play-by-play and gold.win_expectancy (win_expectancy_matrix_build.sql).
--
-- Real definition (FanGraphs, https://library.fangraphs.com/misc/li/,
-- verified directly 2026-08-25): LI is the potential win-expectancy swing
-- of a situation, normalized so 1.0 is average. Rather than model outcome
-- probabilities separately, this measures the REAL observed swing directly:
-- for every real historical play, look up WE entering the play (from
-- gold.win_expectancy) and WE entering the very next real play in that same
-- game (its own next-state's WE, or the final win/loss outcome if it was
-- the last play of the game) -- the actual, real |change in win
-- expectancy| that occurred. Averaging this per (inning, half, outs, base
-- state, margin) state gives each state's average real swing; dividing by
-- the swing averaged across every state (so the league-wide average state
-- is exactly LI=1.0, matching the standard convention) gives Leverage Index.
--
-- Pooled across all seasons (not per-season like gold.win_expectancy/
-- gold.run_expectancy_24): leverage's inning/outs/base/margin *shape* is
-- stable across eras even though raw run-scoring rates aren't, and pooling
-- gives far better sample sizes for the rarer extreme states (e.g. bases
-- loaded, 9th inning, tied) that would be thin within any single season.

WITH game_winner AS (
    SELECT g.retro_game_id, (g.home_score > g.away_score) AS home_won
    FROM core.game g
    WHERE g.game_type = 'regular' AND g.home_score IS NOT NULL AND g.away_score IS NOT NULL
),

event_state AS (
    SELECT
        re.game_id, re.event_id, re._season::integer AS season,
        LEAST(re.inn_ct::integer, 9) AS inning_bucket,
        (re.bat_home_id = '1') AS is_bottom,
        re.outs_ct::smallint AS outs_before,
        (
            (CASE WHEN re.base1_run_id IS NOT NULL AND re.base1_run_id != '' THEN '1' ELSE '0' END)
            || (CASE WHEN re.base2_run_id IS NOT NULL AND re.base2_run_id != '' THEN '1' ELSE '0' END)
            || (CASE WHEN re.base3_run_id IS NOT NULL AND re.base3_run_id != '' THEN '1' ELSE '0' END)
        ) AS base_state,
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

with_next AS (
    SELECT es.*,
        LEAD(inning_bucket) OVER (PARTITION BY game_id ORDER BY event_id) AS next_inning,
        LEAD(is_bottom) OVER (PARTITION BY game_id ORDER BY event_id) AS next_is_bottom,
        LEAD(outs_before) OVER (PARTITION BY game_id ORDER BY event_id) AS next_outs,
        LEAD(base_state) OVER (PARTITION BY game_id ORDER BY event_id) AS next_base_state,
        LEAD(margin_bucket) OVER (PARTITION BY game_id ORDER BY event_id) AS next_margin
    FROM event_state es
    WHERE base_state IN ('000', '100', '010', '001', '110', '101', '011', '111')
),

we_before AS (
    SELECT wn.*, we1.home_win_pct AS we_before
    FROM with_next wn
    JOIN gold.win_expectancy we1 ON we1.season = wn.season AND we1.inning_bucket = wn.inning_bucket
        AND we1.is_bottom = wn.is_bottom AND we1.outs_before = wn.outs_before
        AND we1.base_state = wn.base_state AND we1.margin_bucket = wn.margin_bucket
),

we_swing AS (
    SELECT wb.*,
        ABS(
            COALESCE(we2.home_win_pct, CASE WHEN wb.home_won THEN 1.0 ELSE 0.0 END) - wb.we_before
        ) AS swing
    FROM we_before wb
    LEFT JOIN gold.win_expectancy we2 ON wb.next_inning IS NOT NULL
        AND we2.season = wb.season AND we2.inning_bucket = wb.next_inning
        AND we2.is_bottom = wb.next_is_bottom AND we2.outs_before = wb.next_outs
        AND we2.base_state = wb.next_base_state AND we2.margin_bucket = wb.next_margin
),

global_avg AS (
    SELECT avg(swing) AS avg_swing FROM we_swing
),

matrix_agg AS (
    SELECT
        ws.inning_bucket, ws.is_bottom, ws.outs_before, ws.base_state, ws.margin_bucket,
        ROUND((AVG(ws.swing) / ga.avg_swing)::numeric, 4) AS leverage_index,
        COUNT(*)::integer AS sample_size
    FROM we_swing ws, global_avg ga
    GROUP BY ws.inning_bucket, ws.is_bottom, ws.outs_before, ws.base_state, ws.margin_bucket, ga.avg_swing
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
