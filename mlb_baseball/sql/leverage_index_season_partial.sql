-- Computes ONE season's real win-expectancy-swing sums per state, into the
-- staging table gold.leverage_index_staging -- the chunked replacement for
-- running leverage_index_matrix_build.sql's full logic across all ~123
-- real seasons (1900-2025) in one blind, unobservable query. Confirmed
-- directly: the single-query version ran for 4.5+ hours against real
-- production with no way to tell whether it was making progress (Postgres
-- has no progress view for a plain SELECT/INSERT); this version processes
-- one season (~1/123rd of the real data) per call, so real per-season
-- timing and row counts are directly observable from Python between calls.
--
-- Same real definition and per-play swing computation as
-- leverage_index_matrix_build.sql (FanGraphs LI definition, LEAD()-based
-- next-state lookup, game-ending win/loss fallback) -- see that file's
-- header for the full citation and reasoning, unchanged here. The only
-- difference is WHERE re._season = %(season)s scoping every CTE to one
-- season, and storing SUM(swing)/COUNT(*) per state instead of the final
-- AVG directly, so leverage_index_matrix_finalize.sql can correctly pool
-- the exact same real sums across every season afterward (SUM/COUNT
-- decomposes exactly the same as a single-pass AVG would -- this is a
-- chunking of the computation, not an approximation of it).

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
        AND re._season::integer = %(season)s
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
)

INSERT INTO gold.leverage_index_staging (
    season, inning_bucket, is_bottom, outs_before, base_state, margin_bucket,
    swing_sum, swing_count
)
SELECT
    %(season)s, inning_bucket, is_bottom, outs_before, base_state, margin_bucket,
    SUM(swing), COUNT(*)::integer
FROM we_swing
GROUP BY inning_bucket, is_bottom, outs_before, base_state, margin_bucket
ON CONFLICT (season, inning_bucket, is_bottom, outs_before, base_state, margin_bucket)
DO UPDATE SET
    swing_sum = EXCLUDED.swing_sum,
    swing_count = EXCLUDED.swing_count;
