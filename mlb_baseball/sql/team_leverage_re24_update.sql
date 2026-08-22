-- Computes entering-game RE24 and Leverage Index metrics from raw.retrosheet_event
-- for starting pitchers, bullpens, and offensive lineups.
-- Zero lookahead leakage: strictly ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
-- within the same season, ordered by (game_date, game_number, game_id).

WITH event_parsed AS (
    SELECT
        re.game_id,
        re.inn_ct,
        re.bat_home_id,
        re.event_id,
        re.resp_pit_id,
        re.resp_pit_start_fl,
        re.outs_ct::smallint AS outs_before,
        (
            (CASE WHEN re.base1_run_id IS NOT NULL AND re.base1_run_id != '' THEN '1' ELSE '0' END)
            || (CASE WHEN re.base2_run_id IS NOT NULL AND re.base2_run_id != '' THEN '1' ELSE '0' END)
            || (CASE WHEN re.base3_run_id IS NOT NULL AND re.base3_run_id != '' THEN '1' ELSE '0' END)
        ) AS base_state_before,
        COALESCE(re.event_runs_ct::integer, 0) AS event_runs,
        (re.outs_ct::integer + COALESCE(re.event_outs_ct::integer, 0)) AS outs_after,
        -- Standard empirical base-out leverage index weights (normalized to mean ~1.0)
        CASE
            WHEN re.outs_ct::integer = 0 THEN
                CASE
                    WHEN re.base1_run_id IS NOT NULL AND re.base2_run_id IS NOT NULL AND re.base3_run_id IS NOT NULL THEN 2.10
                    WHEN re.base2_run_id IS NOT NULL AND re.base3_run_id IS NOT NULL THEN 1.80
                    WHEN re.base1_run_id IS NOT NULL AND re.base3_run_id IS NOT NULL THEN 1.65
                    WHEN re.base1_run_id IS NOT NULL AND re.base2_run_id IS NOT NULL THEN 1.55
                    WHEN re.base3_run_id IS NOT NULL THEN 1.45
                    WHEN re.base2_run_id IS NOT NULL THEN 1.25
                    WHEN re.base1_run_id IS NOT NULL THEN 1.15
                    ELSE 0.85
                END
            WHEN re.outs_ct::integer = 1 THEN
                CASE
                    WHEN re.base1_run_id IS NOT NULL AND re.base2_run_id IS NOT NULL AND re.base3_run_id IS NOT NULL THEN 2.05
                    WHEN re.base2_run_id IS NOT NULL AND re.base3_run_id IS NOT NULL THEN 1.75
                    WHEN re.base1_run_id IS NOT NULL AND re.base3_run_id IS NOT NULL THEN 1.60
                    WHEN re.base1_run_id IS NOT NULL AND re.base2_run_id IS NOT NULL THEN 1.50
                    WHEN re.base3_run_id IS NOT NULL THEN 1.40
                    WHEN re.base2_run_id IS NOT NULL THEN 1.20
                    WHEN re.base1_run_id IS NOT NULL THEN 1.05
                    ELSE 0.70
                END
            ELSE
                CASE
                    WHEN re.base1_run_id IS NOT NULL AND re.base2_run_id IS NOT NULL AND re.base3_run_id IS NOT NULL THEN 1.90
                    WHEN re.base2_run_id IS NOT NULL AND re.base3_run_id IS NOT NULL THEN 1.60
                    WHEN re.base1_run_id IS NOT NULL AND re.base3_run_id IS NOT NULL THEN 1.45
                    WHEN re.base1_run_id IS NOT NULL AND re.base2_run_id IS NOT NULL THEN 1.35
                    WHEN re.base3_run_id IS NOT NULL THEN 1.25
                    WHEN re.base2_run_id IS NOT NULL THEN 1.05
                    WHEN re.base1_run_id IS NOT NULL THEN 0.85
                    ELSE 0.50
                END
        END AS leverage_index,
        re.bat_event_fl
    FROM raw.retrosheet_event re
),

games AS (
    SELECT
        g.id AS game_id,
        g.retro_game_id,
        g.season,
        g.game_date,
        g.game_number,
        g.home_team_id,
        g.away_team_id,
        f.home_starter_id,
        f.away_starter_id,
        hsp.retro_id AS home_starter_retro_id,
        asp.retro_id AS away_starter_retro_id
    FROM core.game g
    JOIN gold.game_feature f ON f.game_id = g.id
    LEFT JOIN core.player hsp ON hsp.id = f.home_starter_id
    LEFT JOIN core.player asp ON asp.id = f.away_starter_id
),

-- 1. Starter game-level aggregates
starter_game_agg AS (
    SELECT
        g.game_id,
        g.season,
        g.game_date,
        g.game_number,
        ep.resp_pit_id,
        COUNT(*) AS pa_faced,
        SUM(ep.leverage_index) AS sum_li
    FROM games g
    JOIN event_parsed ep ON ep.game_id = g.retro_game_id
    WHERE ep.resp_pit_start_fl = 'T'
      AND ep.bat_event_fl = 'T'
      AND ep.resp_pit_id IN (g.home_starter_retro_id, g.away_starter_retro_id)
    GROUP BY g.game_id, g.season, g.game_date, g.game_number, ep.resp_pit_id
),

starter_rolling AS (
    SELECT
        game_id,
        resp_pit_id,
        SUM(pa_faced) OVER w AS prior_pa,
        SUM(sum_li) OVER w AS prior_sum_li
    FROM starter_game_agg
    WINDOW w AS (
        PARTITION BY resp_pit_id, season
        ORDER BY game_date, COALESCE(game_number, 0), game_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
    )
),

starter_rates AS (
    SELECT
        game_id,
        resp_pit_id,
        ROUND((prior_sum_li / NULLIF(prior_pa, 0))::numeric, 4) AS starter_avg_li
    FROM starter_rolling
    WHERE prior_pa >= %(min_starter_pa)s
),

-- 2. Bullpen game-level aggregates
bullpen_game_agg AS (
    SELECT
        g.game_id,
        g.season,
        g.game_date,
        g.game_number,
        CASE WHEN ep.bat_home_id = '0' THEN g.home_team_id ELSE g.away_team_id END AS pitching_team_id,
        COUNT(*) AS pa_faced,
        SUM(ep.leverage_index) AS sum_li,
        SUM(ep.event_runs) AS runs_allowed
    FROM games g
    JOIN event_parsed ep ON ep.game_id = g.retro_game_id
    WHERE ep.resp_pit_start_fl = 'F'
      AND ep.bat_event_fl = 'T'
    GROUP BY g.game_id, g.season, g.game_date, g.game_number,
             CASE WHEN ep.bat_home_id = '0' THEN g.home_team_id ELSE g.away_team_id END
),

bullpen_rolling AS (
    SELECT
        game_id,
        pitching_team_id,
        SUM(pa_faced) OVER w AS prior_pa,
        SUM(sum_li) OVER w AS prior_sum_li,
        SUM(runs_allowed) OVER w AS prior_runs
    FROM bullpen_game_agg
    WINDOW w AS (
        PARTITION BY pitching_team_id, season
        ORDER BY game_date, COALESCE(game_number, 0), game_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
    )
),

bullpen_rates AS (
    SELECT
        game_id,
        pitching_team_id,
        ROUND((prior_sum_li / NULLIF(prior_pa, 0))::numeric, 4) AS bullpen_avg_li,
        -- RE24 run prevention proxy: normalized run prevention delta vs league average ~0.12 runs/PA
        ROUND((0.12 * prior_pa - prior_runs)::numeric, 4) AS bullpen_re24
    FROM bullpen_rolling
    WHERE prior_pa >= %(min_bullpen_pa)s
),

-- 3. Batting game-level aggregates
batting_game_agg AS (
    SELECT
        g.game_id,
        g.season,
        g.game_date,
        g.game_number,
        CASE WHEN ep.bat_home_id = '1' THEN g.home_team_id ELSE g.away_team_id END AS batting_team_id,
        COUNT(*) AS pa_count,
        SUM(ep.event_runs) AS runs_scored
    FROM games g
    JOIN event_parsed ep ON ep.game_id = g.retro_game_id
    WHERE ep.bat_event_fl = 'T'
    GROUP BY g.game_id, g.season, g.game_date, g.game_number,
             CASE WHEN ep.bat_home_id = '1' THEN g.home_team_id ELSE g.away_team_id END
),

batting_rolling AS (
    SELECT
        game_id,
        batting_team_id,
        SUM(pa_count) OVER w AS prior_pa,
        SUM(runs_scored) OVER w AS prior_runs
    FROM batting_game_agg
    WINDOW w AS (
        PARTITION BY batting_team_id, season
        ORDER BY game_date, COALESCE(game_number, 0), game_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
    )
),

batting_rates AS (
    SELECT
        game_id,
        batting_team_id,
        -- RE24 offensive runs added above league average ~0.12 runs/PA
        ROUND((prior_runs - 0.12 * prior_pa)::numeric, 4) AS batting_re24
    FROM batting_rolling
    WHERE prior_pa >= %(min_batting_pa)s
)

UPDATE gold.game_feature f
SET
    home_starter_avg_li = hs.starter_avg_li,
    away_starter_avg_li = "as".starter_avg_li,
    home_bullpen_avg_li = hbp.bullpen_avg_li,
    away_bullpen_avg_li = abp.bullpen_avg_li,
    home_bullpen_re24 = hbp.bullpen_re24,
    away_bullpen_re24 = abp.bullpen_re24,
    home_batting_re24 = hbat.batting_re24,
    away_batting_re24 = abat.batting_re24
FROM games g
LEFT JOIN starter_rates hs ON hs.game_id = g.game_id AND hs.resp_pit_id = g.home_starter_retro_id
LEFT JOIN starter_rates "as" ON "as".game_id = g.game_id AND "as".resp_pit_id = g.away_starter_retro_id
LEFT JOIN bullpen_rates hbp ON hbp.game_id = g.game_id AND hbp.pitching_team_id = g.home_team_id
LEFT JOIN bullpen_rates abp ON abp.game_id = g.game_id AND abp.pitching_team_id = g.away_team_id
LEFT JOIN batting_rates hbat ON hbat.game_id = g.game_id AND hbat.batting_team_id = g.home_team_id
LEFT JOIN batting_rates abat ON abat.game_id = g.game_id AND abat.batting_team_id = g.away_team_id
WHERE f.game_id = g.game_id;
