-- Prior rolling starter and bullpen xFIP, SIERA, and platoon handedness splits (PIT-06, PLN-03).
-- Computes zero-lookahead entering rates using expanding season-to-date windows.

WITH regular_games AS (
    SELECT g.id AS game_id, g.season, g.game_date, g.game_number, g.retro_game_id,
           g.home_team_id, g.away_team_id,
           hsp.retro_id AS home_starter_retro_id,
           asp.retro_id AS away_starter_retro_id
    FROM core.game g
    LEFT JOIN gold.game_feature f ON f.game_id = g.id
    LEFT JOIN core.player hsp ON hsp.id = f.home_starter_id
    LEFT JOIN core.player asp ON asp.id = f.away_starter_id
    WHERE g.game_type = 'regular'
),

event_parsed AS (
    SELECT
        re.game_id,
        re.bat_home_id,
        re.resp_pit_id,
        re.resp_pit_start_fl,
        re.event_cd,
        re.bat_event_fl,
        re.event_outs_ct::integer AS event_outs_ct,
        re.battedball_cd,
        re.h_cd,
        COALESCE(re.bat_hand_cd, re.resp_bat_hand_cd) AS bat_hand
    FROM raw.retrosheet_event re
    JOIN raw.retrosheet_gameinfo gi ON gi.gid = re.game_id AND lower(gi.gametype) = 'regular'
    WHERE re.resp_pit_id IS NOT NULL AND re.resp_pit_id != ''
),

-- 1. Starting pitcher game-level aggregates
starter_game_agg AS (
    SELECT
        g.game_id,
        g.season,
        g.game_date,
        g.game_number,
        ep.resp_pit_id,
        COUNT(*) AS pa_faced,
        SUM(ep.event_outs_ct) AS outs_rec,
        COUNT(*) FILTER (WHERE ep.battedball_cd = 'F' OR ((ep.event_cd = '23' OR ep.h_cd = '4') AND (ep.battedball_cd IS NULL OR ep.battedball_cd = ''))) AS fb_cnt,
        COUNT(*) FILTER (WHERE ep.battedball_cd = 'G') AS gb_cnt,
        COUNT(*) FILTER (WHERE ep.battedball_cd = 'P') AS pu_cnt,
        COUNT(*) FILTER (WHERE ep.event_cd = '3') AS k_cnt,
        COUNT(*) FILTER (WHERE ep.event_cd IN ('14', '15')) AS bb_cnt,
        COUNT(*) FILTER (WHERE ep.event_cd = '16') AS hbp_cnt,
        -- LHB splits
        COUNT(*) FILTER (WHERE ep.bat_hand = 'L') AS pa_lhb,
        COUNT(*) FILTER (WHERE ep.bat_hand = 'L' AND ep.event_cd = '3') AS k_lhb,
        COUNT(*) FILTER (WHERE ep.bat_hand = 'L' AND ep.event_cd = '14') AS ubb_lhb,
        COUNT(*) FILTER (WHERE ep.bat_hand = 'L' AND ep.event_cd = '16') AS hbp_lhb,
        COUNT(*) FILTER (WHERE ep.bat_hand = 'L' AND ep.event_cd = '20') AS b1_lhb,
        COUNT(*) FILTER (WHERE ep.bat_hand = 'L' AND ep.event_cd = '21') AS b2_lhb,
        COUNT(*) FILTER (WHERE ep.bat_hand = 'L' AND ep.event_cd = '22') AS b3_lhb,
        COUNT(*) FILTER (WHERE ep.bat_hand = 'L' AND (ep.event_cd = '23' OR ep.h_cd = '4')) AS hr_lhb,
        -- RHB splits
        COUNT(*) FILTER (WHERE ep.bat_hand = 'R') AS pa_rhb,
        COUNT(*) FILTER (WHERE ep.bat_hand = 'R' AND ep.event_cd = '3') AS k_rhb,
        COUNT(*) FILTER (WHERE ep.bat_hand = 'R' AND ep.event_cd = '14') AS ubb_rhb,
        COUNT(*) FILTER (WHERE ep.bat_hand = 'R' AND ep.event_cd = '16') AS hbp_rhb,
        COUNT(*) FILTER (WHERE ep.bat_hand = 'R' AND ep.event_cd = '20') AS b1_rhb,
        COUNT(*) FILTER (WHERE ep.bat_hand = 'R' AND ep.event_cd = '21') AS b2_rhb,
        COUNT(*) FILTER (WHERE ep.bat_hand = 'R' AND ep.event_cd = '22') AS b3_rhb,
        COUNT(*) FILTER (WHERE ep.bat_hand = 'R' AND (ep.event_cd = '23' OR ep.h_cd = '4')) AS hr_rhb
    FROM regular_games g
    JOIN event_parsed ep ON ep.game_id = g.retro_game_id
    WHERE ep.resp_pit_start_fl = 'T'
      AND ep.bat_event_fl = 'T'
    GROUP BY g.game_id, g.season, g.game_date, g.game_number, ep.resp_pit_id
),

starter_rolling AS (
    SELECT
        game_id,
        resp_pit_id,
        SUM(pa_faced) OVER w AS prior_pa,
        SUM(outs_rec) OVER w AS prior_outs,
        SUM(fb_cnt) OVER w AS prior_fb,
        SUM(gb_cnt) OVER w AS prior_gb,
        SUM(pu_cnt) OVER w AS prior_pu,
        SUM(k_cnt) OVER w AS prior_k,
        SUM(bb_cnt) OVER w AS prior_bb,
        SUM(hbp_cnt) OVER w AS prior_hbp,
        SUM(pa_lhb) OVER w AS prior_pa_lhb,
        SUM(k_lhb) OVER w AS prior_k_lhb,
        SUM(ubb_lhb) OVER w AS prior_ubb_lhb,
        SUM(hbp_lhb) OVER w AS prior_hbp_lhb,
        SUM(b1_lhb) OVER w AS prior_b1_lhb,
        SUM(b2_lhb) OVER w AS prior_b2_lhb,
        SUM(b3_lhb) OVER w AS prior_b3_lhb,
        SUM(hr_lhb) OVER w AS prior_hr_lhb,
        SUM(pa_rhb) OVER w AS prior_pa_rhb,
        SUM(k_rhb) OVER w AS prior_k_rhb,
        SUM(ubb_rhb) OVER w AS prior_ubb_rhb,
        SUM(hbp_rhb) OVER w AS prior_hbp_rhb,
        SUM(b1_rhb) OVER w AS prior_b1_rhb,
        SUM(b2_rhb) OVER w AS prior_b2_rhb,
        SUM(b3_rhb) OVER w AS prior_b3_rhb,
        SUM(hr_rhb) OVER w AS prior_hr_rhb
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
        -- xFIP: ((13 * 0.105 * FB + 3 * (BB + HBP) - 2 * K) / IP) + 3.10
        CASE
            WHEN prior_pa >= %(min_starter_pa)s AND prior_outs >= 9 THEN
                ROUND((
                    (13.0 * (0.105 * prior_fb) + 3.0 * (prior_bb + prior_hbp) - 2.0 * prior_k)
                    / (prior_outs / 3.0) + 3.10
                )::numeric, 4)
            ELSE NULL
        END AS starter_xfip,
        -- SIERA
        CASE
            WHEN prior_pa >= %(min_starter_pa)s THEN
                ROUND((
                    6.145
                    - 16.984 * (prior_k::numeric / NULLIF(prior_pa, 0))
                    + 11.434 * (prior_bb::numeric / NULLIF(prior_pa, 0))
                    - 1.858 * ((prior_gb - prior_fb - prior_pu)::numeric / NULLIF(prior_pa, 0))
                    + 7.653 * POWER(prior_k::numeric / NULLIF(prior_pa, 0), 2)
                    + 6.664 * POWER(prior_gb::numeric / NULLIF(prior_pa, 0), 2)
                    - 9.096 * (prior_k::numeric / NULLIF(prior_pa, 0)) * (prior_gb::numeric / NULLIF(prior_pa, 0))
                    - 3.037 * (prior_bb::numeric / NULLIF(prior_pa, 0)) * (prior_gb::numeric / NULLIF(prior_pa, 0))
                )::numeric, 4)
            ELSE NULL
        END AS starter_siera,
        -- Platoon LHB
        CASE
            WHEN prior_pa_lhb >= %(min_platoon_pa)s THEN
                ROUND((prior_k_lhb::numeric / NULLIF(prior_pa_lhb, 0))::numeric, 4)
            ELSE NULL
        END AS starter_vs_lhb_k_pct,
        CASE
            WHEN prior_pa_lhb >= %(min_platoon_pa)s THEN
                ROUND((
                    (0.69 * prior_ubb_lhb + 0.72 * prior_hbp_lhb + 0.89 * prior_b1_lhb
                     + 1.27 * prior_b2_lhb + 1.62 * prior_b3_lhb + 2.10 * prior_hr_lhb)
                    / NULLIF(prior_pa_lhb, 0)
                )::numeric, 4)
            ELSE NULL
        END AS starter_vs_lhb_woba,
        -- Platoon RHB
        CASE
            WHEN prior_pa_rhb >= %(min_platoon_pa)s THEN
                ROUND((prior_k_rhb::numeric / NULLIF(prior_pa_rhb, 0))::numeric, 4)
            ELSE NULL
        END AS starter_vs_rhb_k_pct,
        CASE
            WHEN prior_pa_rhb >= %(min_platoon_pa)s THEN
                ROUND((
                    (0.69 * prior_ubb_rhb + 0.72 * prior_hbp_rhb + 0.89 * prior_b1_rhb
                     + 1.27 * prior_b2_rhb + 1.62 * prior_b3_rhb + 2.10 * prior_hr_rhb)
                    / NULLIF(prior_pa_rhb, 0)
                )::numeric, 4)
            ELSE NULL
        END AS starter_vs_rhb_woba
    FROM starter_rolling
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
        SUM(ep.event_outs_ct) AS outs_rec,
        COUNT(*) FILTER (WHERE ep.battedball_cd = 'F' OR ((ep.event_cd = '23' OR ep.h_cd = '4') AND (ep.battedball_cd IS NULL OR ep.battedball_cd = ''))) AS fb_cnt,
        COUNT(*) FILTER (WHERE ep.battedball_cd = 'G') AS gb_cnt,
        COUNT(*) FILTER (WHERE ep.battedball_cd = 'P') AS pu_cnt,
        COUNT(*) FILTER (WHERE ep.event_cd = '3') AS k_cnt,
        COUNT(*) FILTER (WHERE ep.event_cd IN ('14', '15')) AS bb_cnt,
        COUNT(*) FILTER (WHERE ep.event_cd = '16') AS hbp_cnt
    FROM regular_games g
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
        SUM(outs_rec) OVER w AS prior_outs,
        SUM(fb_cnt) OVER w AS prior_fb,
        SUM(gb_cnt) OVER w AS prior_gb,
        SUM(pu_cnt) OVER w AS prior_pu,
        SUM(k_cnt) OVER w AS prior_k,
        SUM(bb_cnt) OVER w AS prior_bb,
        SUM(hbp_cnt) OVER w AS prior_hbp
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
        CASE
            WHEN prior_pa >= %(min_bullpen_pa)s AND prior_outs >= 9 THEN
                ROUND((
                    (13.0 * (0.105 * prior_fb) + 3.0 * (prior_bb + prior_hbp) - 2.0 * prior_k)
                    / (prior_outs / 3.0) + 3.10
                )::numeric, 4)
            ELSE NULL
        END AS bullpen_xfip,
        CASE
            WHEN prior_pa >= %(min_bullpen_pa)s THEN
                ROUND((
                    6.145
                    - 16.984 * (prior_k::numeric / NULLIF(prior_pa, 0))
                    + 11.434 * (prior_bb::numeric / NULLIF(prior_pa, 0))
                    - 1.858 * ((prior_gb - prior_fb - prior_pu)::numeric / NULLIF(prior_pa, 0))
                    + 7.653 * POWER(prior_k::numeric / NULLIF(prior_pa, 0), 2)
                    + 6.664 * POWER(prior_gb::numeric / NULLIF(prior_pa, 0), 2)
                    - 9.096 * (prior_k::numeric / NULLIF(prior_pa, 0)) * (prior_gb::numeric / NULLIF(prior_pa, 0))
                    - 3.037 * (prior_bb::numeric / NULLIF(prior_pa, 0)) * (prior_gb::numeric / NULLIF(prior_pa, 0))
                )::numeric, 4)
            ELSE NULL
        END AS bullpen_siera
    FROM bullpen_rolling
)

UPDATE gold.game_feature f
SET
    home_starter_xfip = h_sr.starter_xfip,
    home_starter_siera = h_sr.starter_siera,
    home_starter_vs_lhb_woba = h_sr.starter_vs_lhb_woba,
    home_starter_vs_rhb_woba = h_sr.starter_vs_rhb_woba,
    home_starter_vs_lhb_k_pct = h_sr.starter_vs_lhb_k_pct,
    home_starter_vs_rhb_k_pct = h_sr.starter_vs_rhb_k_pct,
    away_starter_xfip = a_sr.starter_xfip,
    away_starter_siera = a_sr.starter_siera,
    away_starter_vs_lhb_woba = a_sr.starter_vs_lhb_woba,
    away_starter_vs_rhb_woba = a_sr.starter_vs_rhb_woba,
    away_starter_vs_lhb_k_pct = a_sr.starter_vs_lhb_k_pct,
    away_starter_vs_rhb_k_pct = a_sr.starter_vs_rhb_k_pct,
    home_bullpen_xfip = h_bpr.bullpen_xfip,
    home_bullpen_siera = h_bpr.bullpen_siera,
    away_bullpen_xfip = a_bpr.bullpen_xfip,
    away_bullpen_siera = a_bpr.bullpen_siera
FROM regular_games g
LEFT JOIN starter_rates h_sr ON h_sr.game_id = g.game_id AND h_sr.resp_pit_id = g.home_starter_retro_id
LEFT JOIN starter_rates a_sr ON a_sr.game_id = g.game_id AND a_sr.resp_pit_id = g.away_starter_retro_id
LEFT JOIN bullpen_rates h_bpr ON h_bpr.game_id = g.game_id AND h_bpr.pitching_team_id = g.home_team_id
LEFT JOIN bullpen_rates a_bpr ON a_bpr.game_id = g.game_id AND a_bpr.pitching_team_id = g.away_team_id
WHERE f.game_id = g.game_id;
