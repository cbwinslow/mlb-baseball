WITH regular_games AS (
    SELECT g.id AS game_id, g.season, g.game_date, g.game_pk,
        g.home_team_id, g.away_team_id
    FROM core.game g
    WHERE g.game_type = 'regular' AND g.game_pk IS NOT NULL
),
first_pitcher AS (
    SELECT DISTINCT ON (game_pk, half_inning) game_pk, half_inning, pitcher_id
    FROM raw.mlb_playbyplay
    ORDER BY game_pk, half_inning, at_bat_index::int
),
starters AS (
    SELECT rg.game_id,
        h.pitcher_id AS home_starter_id, a.pitcher_id AS away_starter_id
    FROM regular_games rg
    JOIN first_pitcher h ON h.game_pk = rg.game_pk AND h.half_inning = 'top'
    JOIN first_pitcher a ON a.game_pk = rg.game_pk AND a.half_inning = 'bottom'
),
play_outs AS (
    SELECT game_pk, pitcher_id, half_inning, event_type,
        outs::int - LAG(outs::int, 1, 0) OVER (
            PARTITION BY game_pk, inning, half_inning ORDER BY at_bat_index::int
        ) AS outs_this_play
    FROM raw.mlb_playbyplay
),
pitcher_game_stats AS (
    SELECT rg.game_id, rg.season, rg.game_date,
        (po.half_inning = 'top') AS is_home_pitcher,
        CASE WHEN po.half_inning = 'top' THEN rg.home_team_id ELSE rg.away_team_id END AS team_id,
        po.pitcher_id,
        count(*) FILTER (WHERE po.event_type IN ('strikeout', 'strikeout_double_play')) AS k,
        count(*) FILTER (WHERE po.event_type IN ('walk', 'intent_walk')) AS bb,
        count(*) FILTER (WHERE po.event_type = 'home_run') AS hr,
        count(*) FILTER (WHERE po.event_type NOT IN (
            'caught_stealing_2b', 'caught_stealing_3b', 'caught_stealing_home',
            'pickoff_1b', 'pickoff_2b', 'pickoff_3b',
            'pickoff_caught_stealing_2b', 'pickoff_caught_stealing_3b',
            'wild_pitch', 'game_advisory'
        )) AS bf,
        sum(po.outs_this_play) AS outs
    FROM regular_games rg
    JOIN play_outs po ON po.game_pk = rg.game_pk
    GROUP BY rg.game_id, rg.season, rg.game_date, po.half_inning,
        rg.home_team_id, rg.away_team_id, po.pitcher_id
),
relief_only AS (
    SELECT pgs.game_id, pgs.team_id, pgs.k, pgs.bb, pgs.hr, pgs.bf, pgs.outs
    FROM pitcher_game_stats pgs
    JOIN starters s ON s.game_id = pgs.game_id
    WHERE pgs.pitcher_id IS DISTINCT FROM
        CASE WHEN pgs.is_home_pitcher THEN s.home_starter_id ELSE s.away_starter_id END
),
team_game AS (
    SELECT game_id, season, game_date, home_team_id AS team_id FROM regular_games
    UNION ALL
    SELECT game_id, season, game_date, away_team_id AS team_id FROM regular_games
),
team_relief_game AS (
    SELECT tg.game_id, tg.season, tg.game_date, tg.team_id,
        COALESCE(sum(ro.k), 0) AS k, COALESCE(sum(ro.bb), 0) AS bb,
        COALESCE(sum(ro.hr), 0) AS hr,
        COALESCE(sum(ro.bf), 0) AS bf, COALESCE(sum(ro.outs), 0) AS outs
    FROM team_game tg
    LEFT JOIN relief_only ro ON ro.game_id = tg.game_id AND ro.team_id = tg.team_id
    GROUP BY tg.game_id, tg.season, tg.game_date, tg.team_id
),
rolling_quality AS (
    SELECT game_id, team_id,
        SUM(k) OVER w AS k_sum, SUM(bb) OVER w AS bb_sum,
        SUM(hr) OVER w AS hr_sum, SUM(bf) OVER w AS bf_sum, SUM(outs) OVER w AS outs_sum
    FROM team_relief_game
    WINDOW w AS (
        PARTITION BY team_id, season ORDER BY game_date, game_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
    )
),
quality AS (
    SELECT game_id, team_id,
        CASE WHEN bf_sum > 0 THEN k_sum::numeric / bf_sum END AS k_pct,
        CASE WHEN bf_sum > 0 THEN bb_sum::numeric / bf_sum END AS bb_pct,
        CASE WHEN outs_sum > 0 THEN
            (13 * hr_sum + 3 * bb_sum - 2 * k_sum)::numeric / (outs_sum / 3.0) + %(fip_constant)s
        END AS fip
    FROM rolling_quality
),
team_day_outs AS (
    SELECT team_id, game_date, sum(outs) AS outs
    FROM team_relief_game
    GROUP BY team_id, game_date
),
team_day_fatigue AS (
    SELECT team_id, game_date,
        SUM(outs) OVER (
            PARTITION BY team_id ORDER BY game_date
            RANGE BETWEEN (%(fatigue_days)s * INTERVAL '1 day') PRECEDING
                AND INTERVAL '1 day' PRECEDING
        ) AS fatigue_outs
    FROM team_day_outs
),
fatigue AS (
    SELECT trg.game_id, trg.team_id, tdf.fatigue_outs
    FROM team_relief_game trg
    JOIN team_day_fatigue tdf ON tdf.team_id = trg.team_id AND tdf.game_date = trg.game_date
)
UPDATE gold.game_feature f
SET
    home_bullpen_fip = hq.fip, home_bullpen_k_pct = hq.k_pct, home_bullpen_bb_pct = hq.bb_pct,
    home_bullpen_fatigue = hf.fatigue_outs,
    away_bullpen_fip = aq.fip, away_bullpen_k_pct = aq.k_pct, away_bullpen_bb_pct = aq.bb_pct,
    away_bullpen_fatigue = af.fatigue_outs
FROM regular_games rg
LEFT JOIN quality hq ON hq.game_id = rg.game_id AND hq.team_id = rg.home_team_id
LEFT JOIN quality aq ON aq.game_id = rg.game_id AND aq.team_id = rg.away_team_id
LEFT JOIN fatigue hf ON hf.game_id = rg.game_id AND hf.team_id = rg.home_team_id
LEFT JOIN fatigue af ON af.game_id = rg.game_id AND af.team_id = rg.away_team_id
WHERE f.game_id = rg.game_id AND f.home_bullpen_fip IS NULL
