MODEL (
  name gold.pitcher_estimators,
  kind INCREMENTAL_BY_TIME_RANGE (
    time_column game_date
  ),
  start '2021-01-01',
  cron '@monthly',
  grain (game_id, pitcher_retro_id),
  description '
    Point-in-time entering pitcher skill estimators (xFIP, SIERA) and platoon
    handedness splits (L/R) for pitchers from raw.retrosheet_event (PIT-06, PLN-03).
    Computes zero-lookahead metrics over expanding season-to-date windows strictly
    before the target game.
  '
);

WITH regular_games AS (
    SELECT g.id AS game_id, g.season, g.game_date, g.game_number, g.retro_game_id
    FROM core.game g
    WHERE g.game_type = 'regular'
),
clean_events AS (
    SELECT
        rg.game_id,
        rg.season,
        rg.game_date,
        rg.game_number,
        re.resp_pit_id AS pitcher_retro_id,
        re.resp_pit_start_fl,
        re.event_cd,
        re.event_outs_ct::integer AS event_outs_ct,
        re.battedball_cd,
        re.h_cd,
        COALESCE(re.bat_hand_cd, re.resp_bat_hand_cd) AS bat_hand
    FROM regular_games rg
    JOIN raw.retrosheet_gameinfo gi ON gi.gid = rg.retro_game_id AND lower(gi.gametype) = 'regular'
    JOIN raw.retrosheet_event re ON re.game_id = rg.retro_game_id
    WHERE re.resp_pit_id IS NOT NULL AND re.resp_pit_id != ''
      AND re.bat_event_fl = 'T'
),
pitcher_game_stats AS (
    SELECT
        game_id,
        season,
        game_date,
        game_number,
        pitcher_retro_id,
        COUNT(*) AS pa_faced,
        SUM(event_outs_ct) AS outs_rec,
        COUNT(*) FILTER (WHERE battedball_cd = 'F' OR ((event_cd = '23' OR h_cd = '4') AND (battedball_cd IS NULL OR battedball_cd = ''))) AS fb_cnt,
        COUNT(*) FILTER (WHERE battedball_cd = 'G') AS gb_cnt,
        COUNT(*) FILTER (WHERE battedball_cd = 'P') AS pu_cnt,
        COUNT(*) FILTER (WHERE event_cd = '3') AS k_cnt,
        COUNT(*) FILTER (WHERE event_cd IN ('14', '15')) AS bb_cnt,
        COUNT(*) FILTER (WHERE event_cd = '16') AS hbp_cnt,
        -- LHB splits
        COUNT(*) FILTER (WHERE bat_hand = 'L') AS pa_lhb,
        COUNT(*) FILTER (WHERE bat_hand = 'L' AND event_cd = '3') AS k_lhb,
        COUNT(*) FILTER (WHERE bat_hand = 'L' AND event_cd = '14') AS ubb_lhb,
        COUNT(*) FILTER (WHERE bat_hand = 'L' AND event_cd = '16') AS hbp_lhb,
        COUNT(*) FILTER (WHERE bat_hand = 'L' AND event_cd = '20') AS b1_lhb,
        COUNT(*) FILTER (WHERE bat_hand = 'L' AND event_cd = '21') AS b2_lhb,
        COUNT(*) FILTER (WHERE bat_hand = 'L' AND event_cd = '22') AS b3_lhb,
        COUNT(*) FILTER (WHERE bat_hand = 'L' AND (event_cd = '23' OR h_cd = '4')) AS hr_lhb,
        -- RHB splits
        COUNT(*) FILTER (WHERE bat_hand = 'R') AS pa_rhb,
        COUNT(*) FILTER (WHERE bat_hand = 'R' AND event_cd = '3') AS k_rhb,
        COUNT(*) FILTER (WHERE bat_hand = 'R' AND event_cd = '14') AS ubb_rhb,
        COUNT(*) FILTER (WHERE bat_hand = 'R' AND event_cd = '16') AS hbp_rhb,
        COUNT(*) FILTER (WHERE bat_hand = 'R' AND event_cd = '20') AS b1_rhb,
        COUNT(*) FILTER (WHERE bat_hand = 'R' AND event_cd = '21') AS b2_rhb,
        COUNT(*) FILTER (WHERE bat_hand = 'R' AND event_cd = '22') AS b3_rhb,
        COUNT(*) FILTER (WHERE bat_hand = 'R' AND (event_cd = '23' OR h_cd = '4')) AS hr_rhb
    FROM clean_events
    GROUP BY game_id, season, game_date, game_number, pitcher_retro_id
),
rolling AS (
    SELECT
        game_id,
        season,
        game_date,
        game_number,
        pitcher_retro_id,
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
    FROM pitcher_game_stats
    WINDOW w AS (
        PARTITION BY pitcher_retro_id, season
        ORDER BY game_date, COALESCE(game_number, 0), game_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
    )
)
SELECT
    game_id,
    pitcher_retro_id,
    game_date,
    CASE
        WHEN prior_pa >= 30 AND prior_outs >= 9 THEN
            ROUND((
                (13.0 * (0.105 * prior_fb) + 3.0 * (prior_bb + prior_hbp) - 2.0 * prior_k)
                / (prior_outs / 3.0) + 3.10
            )::numeric, 4)
        ELSE NULL
    END AS xfip,
    CASE
        WHEN prior_pa >= 30 THEN
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
    END AS siera,
    CASE
        WHEN prior_pa_lhb >= 15 THEN
            ROUND((prior_k_lhb::numeric / NULLIF(prior_pa_lhb, 0))::numeric, 4)
        ELSE NULL
    END AS vs_lhb_k_pct,
    CASE
        WHEN prior_pa_lhb >= 15 THEN
            ROUND((
                (0.69 * prior_ubb_lhb + 0.72 * prior_hbp_lhb + 0.89 * prior_b1_lhb
                 + 1.27 * prior_b2_lhb + 1.62 * prior_b3_lhb + 2.10 * prior_hr_lhb)
                / NULLIF(prior_pa_lhb, 0)
            )::numeric, 4)
        ELSE NULL
    END AS vs_lhb_woba,
    CASE
        WHEN prior_pa_rhb >= 15 THEN
            ROUND((prior_k_rhb::numeric / NULLIF(prior_pa_rhb, 0))::numeric, 4)
        ELSE NULL
    END AS vs_rhb_k_pct,
    CASE
        WHEN prior_pa_rhb >= 15 THEN
            ROUND((
                (0.69 * prior_ubb_rhb + 0.72 * prior_hbp_rhb + 0.89 * prior_b1_rhb
                 + 1.27 * prior_b2_rhb + 1.62 * prior_b3_rhb + 2.10 * prior_hr_rhb)
                / NULLIF(prior_pa_rhb, 0)
            )::numeric, 4)
        ELSE NULL
    END AS vs_rhb_woba
FROM rolling
WHERE game_date BETWEEN @start_date AND @end_date;
