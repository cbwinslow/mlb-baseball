-- Comprehensive Baserunning (wSB, XBT%, UBR, wGDP, BsR Total) from Retrosheet events (RUN-01).
-- Strictly point-in-time correct: computed over preceding games in the season.

WITH regular_games AS (
    SELECT g.id AS game_id, g.season, g.game_date, g.game_number, g.retro_game_id,
        g.home_team_id, g.away_team_id
    FROM core.game g
    WHERE lower(g.game_type) = 'regular'
),

team_game_stats AS (
    SELECT
        rg.game_id, rg.season, rg.game_date, rg.game_number,
        CASE WHEN re.bat_home_id = '1' THEN rg.home_team_id ELSE rg.away_team_id END AS team_id,
        count(*) FILTER (WHERE re.run1_sb_fl = 'T')
            + count(*) FILTER (WHERE re.run2_sb_fl = 'T')
            + count(*) FILTER (WHERE re.run3_sb_fl = 'T') AS sb,
        count(*) FILTER (WHERE re.run1_cs_fl = 'T')
            + count(*) FILTER (WHERE re.run2_cs_fl = 'T')
            + count(*) FILTER (WHERE re.run3_cs_fl = 'T') AS cs,
        count(*) FILTER (WHERE re.bat_event_fl = 'T' AND re.event_cd = '20') AS b1,
        count(*) FILTER (WHERE re.bat_event_fl = 'T' AND re.event_cd = '14') AS ubb,
        count(*) FILTER (WHERE re.bat_event_fl = 'T' AND re.event_cd = '16') AS hbp,
        count(*) FILTER (WHERE re.bat_event_fl = 'T' AND re.gdp_fl = 'T') AS gdp,
        -- Extra bases taken
        count(*) FILTER (
            WHERE (re.event_cd = '20' AND re.run1_dest_id IN ('3', '4', 'H', '5', '6'))
               OR (re.event_cd = '21' AND re.run1_dest_id IN ('4', 'H', '5', '6'))
               OR (re.event_cd = '20' AND re.run2_dest_id IN ('4', 'H', '5', '6'))
        ) AS xbt,
        -- Opportunities
        count(*) FILTER (
            WHERE (re.event_cd = '20' AND (NULLIF(re.base1_run_id, '') IS NOT NULL OR NULLIF(re.base2_run_id, '') IS NOT NULL))
               OR (re.event_cd = '21' AND NULLIF(re.base1_run_id, '') IS NOT NULL)
        ) AS xbt_opp
    FROM regular_games rg
    JOIN raw.retrosheet_gameinfo gi ON gi.gid = rg.retro_game_id AND lower(gi.gametype) = 'regular'
    JOIN raw.retrosheet_event re ON re.game_id = rg.retro_game_id
    GROUP BY rg.game_id, rg.season, rg.game_date, rg.game_number,
        CASE WHEN re.bat_home_id = '1' THEN rg.home_team_id ELSE rg.away_team_id END
),

team_rolling AS (
    SELECT game_id, team_id, season, game_date,
        SUM(sb) OVER w AS sb_sum,
        SUM(cs) OVER w AS cs_sum,
        SUM(b1) OVER w AS b1_sum,
        SUM(ubb) OVER w AS ubb_sum,
        SUM(hbp) OVER w AS hbp_sum,
        SUM(gdp) OVER w AS gdp_sum,
        SUM(xbt) OVER w AS xbt_sum,
        SUM(xbt_opp) OVER w AS xbt_opp_sum
    FROM team_game_stats
    WINDOW w AS (
        PARTITION BY team_id, season ORDER BY game_date, COALESCE(game_number, 0), game_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
    )
),

league_daily AS (
    SELECT season, game_date,
        SUM(sb) AS sb, SUM(cs) AS cs, SUM(b1) AS b1, SUM(ubb) AS ubb, SUM(hbp) AS hbp,
        SUM(xbt) AS xbt, SUM(xbt_opp) AS xbt_opp
    FROM team_game_stats
    GROUP BY season, game_date
),

league_rolling AS (
    SELECT season, game_date,
        SUM(sb) OVER w AS sb_sum,
        SUM(cs) OVER w AS cs_sum,
        SUM(b1) OVER w AS b1_sum,
        SUM(ubb) OVER w AS ubb_sum,
        SUM(hbp) OVER w AS hbp_sum,
        SUM(xbt) OVER w AS xbt_sum,
        SUM(xbt_opp) OVER w AS xbt_opp_sum
    FROM league_daily
    WINDOW w AS (
        PARTITION BY season ORDER BY game_date
        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
    )
),

league_context AS (
    SELECT season, game_date,
        CASE WHEN (b1_sum + ubb_sum + hbp_sum) > 0 THEN
            (COALESCE(sb_sum, 0) * 0.20 + COALESCE(cs_sum, 0) * (-0.42))
                / (b1_sum + ubb_sum + hbp_sum)
        END AS lgwsb,
        CASE WHEN COALESCE(xbt_opp_sum, 0) > 0 THEN
            xbt_sum::numeric / xbt_opp_sum
        ELSE 0.40
        END AS lg_xbt_rate
    FROM league_rolling
),

computed AS (
    SELECT
        tr.game_id,
        tr.team_id,
        tr.sb_sum,
        tr.cs_sum,
        (COALESCE(tr.b1_sum, 0) + COALESCE(tr.ubb_sum, 0) + COALESCE(tr.hbp_sum, 0)) AS opp_sum,
        tr.gdp_sum,
        tr.xbt_sum,
        tr.xbt_opp_sum,
        lg.lgwsb,
        COALESCE(lg.lg_xbt_rate, 0.40) AS lg_xbt_rate
    FROM team_rolling tr
    LEFT JOIN league_context lg ON lg.season = tr.season AND lg.game_date = tr.game_date
),

bsr_metrics AS (
    SELECT
        game_id,
        team_id,
        sb_sum,
        cs_sum,
        -- wSB
        CASE WHEN COALESCE(sb_sum, 0) + COALESCE(cs_sum, 0) >= 5 AND lgwsb IS NOT NULL THEN
            ROUND(COALESCE(sb_sum, 0) * 0.20 + COALESCE(cs_sum, 0) * (-0.42) - lgwsb * opp_sum, 2)
        END AS wsb,

        -- XBT%
        CASE WHEN COALESCE(xbt_opp_sum, 0) >= 5 THEN
            ROUND(xbt_sum::numeric / xbt_opp_sum, 4)
        END AS xbt_pct,

        -- UBR (Ultimate Base Running runs)
        CASE WHEN COALESCE(xbt_opp_sum, 0) >= 5 THEN
            ROUND((xbt_sum::numeric - (xbt_opp_sum * lg_xbt_rate)) * 0.20, 2)
        END AS ubr_runs,

        -- wGDP runs
        CASE WHEN COALESCE(opp_sum, 0) >= 10 THEN
            ROUND(-(COALESCE(gdp_sum, 0) * 0.45), 2)
        END AS wgdp_runs
    FROM computed
),

final_bsr AS (
    SELECT
        game_id,
        team_id,
        sb_sum,
        cs_sum,
        wsb,
        xbt_pct,
        ubr_runs,
        wgdp_runs,
        CASE
            WHEN wsb IS NOT NULL OR ubr_runs IS NOT NULL OR wgdp_runs IS NOT NULL THEN
                ROUND(COALESCE(wsb, 0) + COALESCE(ubr_runs, 0) + COALESCE(wgdp_runs, 0), 2)
            ELSE NULL
        END AS bsr_total
    FROM bsr_metrics
)

UPDATE gold.game_feature f
SET
    home_sb = wh.sb_sum,
    away_sb = wa.sb_sum,
    home_cs = wh.cs_sum,
    away_cs = wa.cs_sum,
    home_wsb = wh.wsb,
    away_wsb = wa.wsb,
    home_xbt_pct = wh.xbt_pct,
    away_xbt_pct = wa.xbt_pct,
    home_ubr_runs = wh.ubr_runs,
    away_ubr_runs = wa.ubr_runs,
    home_wgdp_runs = wh.wgdp_runs,
    away_wgdp_runs = wa.wgdp_runs,
    home_bsr_total = wh.bsr_total,
    away_bsr_total = wa.bsr_total
FROM regular_games rg
LEFT JOIN final_bsr wh ON wh.game_id = rg.game_id AND wh.team_id = rg.home_team_id
LEFT JOIN final_bsr wa ON wa.game_id = rg.game_id AND wa.team_id = rg.away_team_id
WHERE f.game_id = rg.game_id;
