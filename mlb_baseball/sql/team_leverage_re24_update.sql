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
        re._season::integer AS season,
        re.outs_ct::smallint AS outs_before,
        (
            (CASE WHEN re.base1_run_id IS NOT NULL AND re.base1_run_id != '' THEN '1' ELSE '0' END)
            || (CASE WHEN re.base2_run_id IS NOT NULL AND re.base2_run_id != '' THEN '1' ELSE '0' END)
            || (CASE WHEN re.base3_run_id IS NOT NULL AND re.base3_run_id != '' THEN '1' ELSE '0' END)
        ) AS base_state_before,
        COALESCE(re.event_runs_ct::integer, 0) AS event_runs,
        (re.outs_ct::integer + COALESCE(re.event_outs_ct::integer, 0)) AS outs_after,
        LEAST(re.inn_ct::integer, 9) AS inning_bucket,
        (re.bat_home_id = '1') AS is_bottom,
        -- Home-minus-away score margin entering this play, capped to
        -- +/-8, matching leverage_index_matrix_build.sql exactly.
        GREATEST(-8, LEAST(8,
            CASE WHEN re.bat_home_id = '1'
                THEN re.start_bat_score_ct::integer - re.start_fld_score_ct::integer
                ELSE re.start_fld_score_ct::integer - re.start_bat_score_ct::integer
            END
        )) AS margin_bucket,
        re.bat_event_fl
    FROM raw.retrosheet_event re
),

-- Leverage Index: real, empirically derived from gold.leverage_index
-- (ADR-262), not a hand-typed table. A state combination absent from the
-- table (extremely rare -- an under-observed corner of the real historical
-- state space) falls back to 1.0, the definition of average leverage,
-- rather than producing NULL and breaking the SUM aggregation below.
event_with_li AS (
    SELECT ep.*, COALESCE(li.leverage_index, 1.0) AS leverage_index
    FROM event_parsed ep
    LEFT JOIN gold.leverage_index li
        ON li.inning_bucket = ep.inning_bucket
        AND li.is_bottom = ep.is_bottom
        AND li.outs_before = ep.outs_before
        AND li.base_state = ep.base_state_before
        AND li.margin_bucket = ep.margin_bucket
),

-- RE24 (Tom Tango et al., "The Book"; FanGraphs RE24 library page,
-- https://library.fangraphs.com/misc/re24/, fetched and verified directly
-- 2026-08-25): per play, RE24 = RE(state after the play) - RE(state
-- before the play) + runs scored on the play, using the real, per-season
-- empirical gold.run_expectancy_24 (ADR-261/262) -- not the previous
-- made-up "~0.12 runs/PA league average" proxy. The source also confirms
-- RE24 is a CUMULATIVE total (summed across plays/PAs), not a per-PA
-- rate, and that a pitcher's RE24 is exactly the negative of the batting
-- team's RE24 for the same plays ("whatever positive credit goes to the
-- batter is mirrored exactly by the pitcher").
--
-- The "after" state is found via LEAD() over the next real play in the
-- same game, ordered by the real numeric event sequence -- the same
-- technique leverage_index_matrix_build.sql's with_next CTE already uses
-- for its own next-state lookup -- rather than reconstructing base
-- occupancy from bat_dest_id/run1_dest_id/run2_dest_id/run3_dest_id:
-- those columns exist on raw.retrosheet_event, but their exact
-- runner-to-base destination semantics could not be independently
-- confirmed against a real fetched source in this session, so the
-- already-verified LEAD() technique was used instead. Unlike
-- leverage_index_matrix_build.sql (which wants the real next state
-- regardless of half-inning boundary, falling back to the game's
-- win/loss outcome only at the very last play), RE24 only cares about
-- half-inning boundaries: when the play ends the half-inning (outs_after
-- >= 3), RE(after) is 0 by definition -- no more runs are expected that
-- half-inning -- so the after-state lookup is explicitly gated on
-- outs_after < 3 in the join below, rather than trusting the LEAD to
-- land on a missing row (it usually lands on the next half-inning's real
-- leadoff state instead, which must NOT be used as "after").
--
-- Both the before- and after-state lookups are LEFT JOINs, COALESCEd to
-- 0 on a miss -- same "extremely rare state produces NULL, use a sane
-- fallback rather than silently dropping the whole play from every
-- downstream aggregate (including pa_faced/leverage_index, now sourced
-- from this same CTE chain)" reasoning as event_with_li's own fallback
-- above. In practice every (season, outs_before, base_state) combination
-- gets a real gold.run_expectancy_24 row once that season's matrix is
-- built (run_expectancy_matrix_build.sql covers all 8 real base states x
-- 3 out counts), so this only guards against an unbuilt/incomplete
-- season, not normal operation.
event_with_re24 AS (
    SELECT
        eli.*,
        LEAD(eli.outs_before) OVER (
            PARTITION BY eli.game_id ORDER BY eli.event_id::integer
        ) AS next_outs_before,
        LEAD(eli.base_state_before) OVER (
            PARTITION BY eli.game_id ORDER BY eli.event_id::integer
        ) AS next_base_state_before
    FROM event_with_li eli
),

event_re24 AS (
    SELECT
        er.*,
        (
            COALESCE(re_after.runs_rest_of_inning, 0)
            - COALESCE(re_before.runs_rest_of_inning, 0)
            + er.event_runs
        ) AS play_re24
    FROM event_with_re24 er
    LEFT JOIN gold.run_expectancy_24 re_before
        ON re_before.season = er.season
        AND re_before.outs_before = er.outs_before
        AND re_before.base_state = er.base_state_before
    LEFT JOIN gold.run_expectancy_24 re_after
        ON re_after.season = er.season
        AND er.outs_after < 3
        AND re_after.outs_before = er.next_outs_before
        AND re_after.base_state = er.next_base_state_before
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
    JOIN event_with_li ep ON ep.game_id = g.retro_game_id
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
        SUM(ep.event_runs) AS runs_allowed,
        SUM(ep.play_re24) AS sum_re24_conceded
    FROM games g
    JOIN event_re24 ep ON ep.game_id = g.retro_game_id
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
        SUM(runs_allowed) OVER w AS prior_runs,
        SUM(sum_re24_conceded) OVER w AS prior_re24_conceded
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
        -- Real, cumulative RE24 (not a per-PA rate -- see FanGraphs source
        -- note above). play_re24 is computed from the batting team's
        -- perspective; a pitcher's/bullpen's RE24 is the negative of the
        -- RE24 conceded to the batters it faced.
        ROUND((-1 * prior_re24_conceded)::numeric, 4) AS bullpen_re24
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
        SUM(ep.event_runs) AS runs_scored,
        SUM(ep.play_re24) AS sum_re24
    FROM games g
    JOIN event_re24 ep ON ep.game_id = g.retro_game_id
    WHERE ep.bat_event_fl = 'T'
    GROUP BY g.game_id, g.season, g.game_date, g.game_number,
             CASE WHEN ep.bat_home_id = '1' THEN g.home_team_id ELSE g.away_team_id END
),

batting_rolling AS (
    SELECT
        game_id,
        batting_team_id,
        SUM(pa_count) OVER w AS prior_pa,
        SUM(runs_scored) OVER w AS prior_runs,
        SUM(sum_re24) OVER w AS prior_re24
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
        -- Real, cumulative RE24 (not a per-PA rate -- see FanGraphs source
        -- note above): sum of each play's real RE(after) - RE(before) +
        -- runs-scored value, from the batting team's own perspective.
        ROUND(prior_re24::numeric, 4) AS batting_re24
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
