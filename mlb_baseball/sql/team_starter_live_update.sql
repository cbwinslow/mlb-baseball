WITH regular_games AS (
    SELECT g.id AS game_id, g.season, g.game_date, g.game_pk
    FROM core.game g WHERE g.game_type = 'regular' AND g.game_pk IS NOT NULL
),
first_pitcher AS (
    SELECT DISTINCT ON (game_pk, half_inning) game_pk, half_inning, pitcher_id
    FROM raw.mlb_playbyplay ORDER BY game_pk, half_inning, at_bat_index::int
),
starters AS (
    SELECT rg.game_id, h.pitcher_id AS home_starter_id, a.pitcher_id AS away_starter_id
    FROM regular_games rg
    JOIN first_pitcher h ON h.game_pk = rg.game_pk AND h.half_inning = 'top'
    JOIN first_pitcher a ON a.game_pk = rg.game_pk AND a.half_inning = 'bottom'
),
play_outs AS (
    SELECT game_pk, pitcher_id, event_type,
        outs::int - LAG(outs::int, 1, 0) OVER (PARTITION BY game_pk, inning, half_inning ORDER BY at_bat_index::int) AS outs_this_play
    FROM raw.mlb_playbyplay
),
pitcher_game_stats AS (
    SELECT rg.game_id, rg.season, rg.game_date, po.pitcher_id,
        count(*) FILTER (WHERE po.event_type IN ('strikeout', 'strikeout_double_play')) AS k,
        count(*) FILTER (WHERE po.event_type IN ('walk', 'intent_walk')) AS bb,
        count(*) FILTER (WHERE po.event_type = 'home_run') AS hr,
        count(*) FILTER (WHERE po.event_type NOT IN ('caught_stealing_2b', 'caught_stealing_3b', 'caught_stealing_home', 'pickoff_1b', 'pickoff_2b', 'pickoff_3b', 'pickoff_caught_stealing_2b', 'pickoff_caught_stealing_3b', 'wild_pitch', 'game_advisory')) AS bf,
        sum(po.outs_this_play) AS outs
    FROM regular_games rg JOIN play_outs po ON po.game_pk = rg.game_pk
    GROUP BY rg.game_id, rg.season, rg.game_date, po.pitcher_id
),
rolling AS (
    SELECT game_id, pitcher_id, SUM(k) OVER w AS k_sum, SUM(bb) OVER w AS bb_sum,
        SUM(hr) OVER w AS hr_sum, SUM(bf) OVER w AS bf_sum, SUM(outs) OVER w AS outs_sum
    FROM pitcher_game_stats
    WINDOW w AS (PARTITION BY pitcher_id, season ORDER BY game_date, game_id ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING)
),
quality AS (
    SELECT game_id, pitcher_id, CASE WHEN bf_sum > 0 THEN k_sum::numeric / bf_sum END AS k_pct,
        CASE WHEN bf_sum > 0 THEN bb_sum::numeric / bf_sum END AS bb_pct,
        CASE WHEN bf_sum > 0 THEN hr_sum::numeric / bf_sum END AS hr_pct,
        CASE WHEN outs_sum > 0 THEN (13 * hr_sum + 3 * bb_sum - 2 * k_sum)::numeric / (outs_sum / 3.0) + %(fip_constant)s END AS fip
    FROM rolling
)
UPDATE gold.game_feature f
SET home_starter_id = hp.id, home_starter_era = hq.fip, home_starter_k_pct = hq.k_pct,
    home_starter_bb_pct = hq.bb_pct, home_starter_hr_pct = hq.hr_pct,
    away_starter_id = ap.id, away_starter_era = aq.fip, away_starter_k_pct = aq.k_pct,
    away_starter_bb_pct = aq.bb_pct, away_starter_hr_pct = aq.hr_pct
FROM starters s
LEFT JOIN quality hq ON hq.game_id = s.game_id AND hq.pitcher_id = s.home_starter_id
LEFT JOIN quality aq ON aq.game_id = s.game_id AND aq.pitcher_id = s.away_starter_id
LEFT JOIN core.player hp ON hp.mlbam_id = s.home_starter_id
LEFT JOIN core.player ap ON ap.mlbam_id = s.away_starter_id
WHERE f.game_id = s.game_id AND f.home_starter_era IS NULL
