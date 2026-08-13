WITH regular_games AS (
    SELECT g.id AS game_id, g.season, g.game_date, g.retro_game_id
    FROM core.game g WHERE g.game_type = 'regular'
),
pitcher_game_stats AS (
    SELECT rg.game_id, rg.season, rg.game_date, re.resp_pit_id AS pitcher_retro_id,
        count(*) FILTER (WHERE re.bat_event_fl = 'T' AND re.event_cd = '3') AS k,
        count(*) FILTER (WHERE re.bat_event_fl = 'T' AND re.event_cd IN ('14', '15')) AS bb,
        count(*) FILTER (WHERE re.bat_event_fl = 'T' AND re.event_cd = '16') AS hbp,
        count(*) FILTER (WHERE re.bat_event_fl = 'T' AND re.event_cd = '23') AS hr,
        count(*) FILTER (WHERE re.bat_event_fl = 'T') AS bf,
        sum(re.event_outs_ct::numeric) AS outs
    FROM regular_games rg
    JOIN raw.retrosheet_gameinfo gi ON gi.gid = rg.retro_game_id AND lower(gi.gametype) = 'regular'
    JOIN raw.retrosheet_event re ON re.game_id = rg.retro_game_id
    GROUP BY rg.game_id, rg.season, rg.game_date, re.resp_pit_id
),
starters AS (
    SELECT rg.game_id,
        max(re.resp_pit_id) FILTER (WHERE re.bat_home_id = '0') AS home_starter_retro_id,
        max(re.resp_pit_id) FILTER (WHERE re.bat_home_id = '1') AS away_starter_retro_id
    FROM regular_games rg
    JOIN raw.retrosheet_gameinfo gi ON gi.gid = rg.retro_game_id AND lower(gi.gametype) = 'regular'
    JOIN raw.retrosheet_event re ON re.game_id = rg.retro_game_id
    WHERE re.resp_pit_start_fl = 'T'
    GROUP BY rg.game_id
),
rolling AS (
    SELECT game_id, pitcher_retro_id, game_date,
        SUM(k) OVER w_season AS k_sum, SUM(bb) OVER w_season AS bb_sum,
        SUM(hbp) OVER w_season AS hbp_sum, SUM(hr) OVER w_season AS hr_sum,
        SUM(bf) OVER w_season AS bf_sum, SUM(outs) OVER w_season AS outs_sum,
        game_date - LAG(game_date) OVER w_career AS rest
    FROM pitcher_game_stats
    WINDOW
        w_season AS (
            PARTITION BY pitcher_retro_id, season ORDER BY game_date, game_id
            ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
        ),
        w_career AS (PARTITION BY pitcher_retro_id ORDER BY game_date, game_id)
),
quality AS (
    SELECT game_id, pitcher_retro_id, rest,
        CASE WHEN bf_sum > 0 THEN k_sum::numeric / bf_sum END AS k_pct,
        CASE WHEN bf_sum > 0 THEN bb_sum::numeric / bf_sum END AS bb_pct,
        CASE WHEN bf_sum > 0 THEN hr_sum::numeric / bf_sum END AS hr_pct,
        CASE WHEN outs_sum > 0 THEN
            (13 * hr_sum + 3 * (bb_sum + hbp_sum) - 2 * k_sum)::numeric / (outs_sum / 3.0)
                + %(fip_constant)s
        END AS fip
    FROM rolling
)
UPDATE gold.game_feature f
SET home_starter_id = hp.id, home_starter_era = hq.fip, home_starter_k_pct = hq.k_pct,
    home_starter_bb_pct = hq.bb_pct, home_starter_hr_pct = hq.hr_pct, home_starter_rest = hq.rest,
    away_starter_id = ap.id, away_starter_era = aq.fip, away_starter_k_pct = aq.k_pct,
    away_starter_bb_pct = aq.bb_pct, away_starter_hr_pct = aq.hr_pct, away_starter_rest = aq.rest
FROM starters s
LEFT JOIN quality hq ON hq.game_id = s.game_id AND hq.pitcher_retro_id = s.home_starter_retro_id
LEFT JOIN quality aq ON aq.game_id = s.game_id AND aq.pitcher_retro_id = s.away_starter_retro_id
LEFT JOIN core.player hp ON hp.retro_id = s.home_starter_retro_id
LEFT JOIN core.player ap ON ap.retro_id = s.away_starter_retro_id
WHERE f.game_id = s.game_id
