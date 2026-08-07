WITH targets AS (
    SELECT f.id AS feature_id, f.game_date, f.home_team_id, f.away_team_id
    FROM gold.game_feature f
    WHERE f.home_win IS NULL AND f.mlb_game_pk IS NOT NULL AND f.home_bullpen_fip IS NULL
),
regular_games AS (
    SELECT g.id AS game_id, g.game_date, g.game_pk, g.home_team_id, g.away_team_id
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
    SELECT rg.game_id, rg.game_date,
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
    GROUP BY rg.game_id, rg.game_date, po.half_inning,
        rg.home_team_id, rg.away_team_id, po.pitcher_id
),
relief_only AS (
    SELECT pgs.game_date, pgs.team_id, pgs.k, pgs.bb, pgs.hr, pgs.bf, pgs.outs
    FROM pitcher_game_stats pgs
    JOIN starters s ON s.game_id = pgs.game_id
    WHERE pgs.pitcher_id IS DISTINCT FROM
        CASE WHEN pgs.is_home_pitcher THEN s.home_starter_id ELSE s.away_starter_id END
),
home_quality AS (
    SELECT t.feature_id,
        CASE WHEN sum(r.bf) > 0 THEN sum(r.k)::numeric / sum(r.bf) END AS k_pct,
        CASE WHEN sum(r.bf) > 0 THEN sum(r.bb)::numeric / sum(r.bf) END AS bb_pct,
        CASE WHEN sum(r.outs) > 0 THEN
            (13 * sum(r.hr) + 3 * sum(r.bb) - 2 * sum(r.k))::numeric / (sum(r.outs) / 3.0)
                + %(fip_constant)s
        END AS fip
    FROM targets t
    JOIN relief_only r ON r.team_id = t.home_team_id AND r.game_date < t.game_date
    GROUP BY t.feature_id
),
away_quality AS (
    SELECT t.feature_id,
        CASE WHEN sum(r.bf) > 0 THEN sum(r.k)::numeric / sum(r.bf) END AS k_pct,
        CASE WHEN sum(r.bf) > 0 THEN sum(r.bb)::numeric / sum(r.bf) END AS bb_pct,
        CASE WHEN sum(r.outs) > 0 THEN
            (13 * sum(r.hr) + 3 * sum(r.bb) - 2 * sum(r.k))::numeric / (sum(r.outs) / 3.0)
                + %(fip_constant)s
        END AS fip
    FROM targets t
    JOIN relief_only r ON r.team_id = t.away_team_id AND r.game_date < t.game_date
    GROUP BY t.feature_id
),
home_fatigue AS (
    SELECT t.feature_id, sum(r.outs) AS fatigue_outs
    FROM targets t
    JOIN relief_only r ON r.team_id = t.home_team_id
        AND r.game_date < t.game_date
        AND r.game_date >= t.game_date - %(fatigue_days)s
    GROUP BY t.feature_id
),
away_fatigue AS (
    SELECT t.feature_id, sum(r.outs) AS fatigue_outs
    FROM targets t
    JOIN relief_only r ON r.team_id = t.away_team_id
        AND r.game_date < t.game_date
        AND r.game_date >= t.game_date - %(fatigue_days)s
    GROUP BY t.feature_id
)
UPDATE gold.game_feature f
SET
    home_bullpen_fip = hq.fip, home_bullpen_k_pct = hq.k_pct, home_bullpen_bb_pct = hq.bb_pct,
    home_bullpen_fatigue = hf.fatigue_outs,
    away_bullpen_fip = aq.fip, away_bullpen_k_pct = aq.k_pct, away_bullpen_bb_pct = aq.bb_pct,
    away_bullpen_fatigue = af.fatigue_outs
FROM targets t
LEFT JOIN home_quality hq ON hq.feature_id = t.feature_id
LEFT JOIN away_quality aq ON aq.feature_id = t.feature_id
LEFT JOIN home_fatigue hf ON hf.feature_id = t.feature_id
LEFT JOIN away_fatigue af ON af.feature_id = t.feature_id
WHERE f.id = t.feature_id
