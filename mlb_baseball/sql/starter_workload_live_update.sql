WITH regular_games AS (
    SELECT g.id AS game_id, g.season, g.game_date, g.game_pk
    FROM core.game g
    WHERE g.game_type = 'regular' AND g.game_pk IS NOT NULL
),
first_pitcher AS (
    SELECT DISTINCT ON (game_pk, half_inning) game_pk, half_inning, pitcher_id
    FROM raw.mlb_playbyplay
    ORDER BY game_pk, half_inning, at_bat_index::int
),
starters AS (
    SELECT rg.game_id, rg.game_date, h.pitcher_id AS home_starter_id, a.pitcher_id AS away_starter_id
    FROM regular_games rg
    JOIN first_pitcher h ON h.game_pk = rg.game_pk AND h.half_inning = 'top'
    JOIN first_pitcher a ON a.game_pk = rg.game_pk AND a.half_inning = 'bottom'
),
starter_starts AS (
    SELECT
        rg.game_id,
        rg.game_date,
        fp.pitcher_id,
        rg.game_date - LAG(rg.game_date) OVER (
            PARTITION BY fp.pitcher_id ORDER BY rg.game_date, rg.game_id
        ) AS rest_days
    FROM regular_games rg
    JOIN first_pitcher fp ON fp.game_pk = rg.game_pk
    GROUP BY rg.game_id, rg.game_date, fp.pitcher_id
),
play_outs AS (
    SELECT game_pk, pitcher_id,
        outs::int - LAG(outs::int, 1, 0) OVER (
            PARTITION BY game_pk, inning, half_inning ORDER BY at_bat_index::int
        ) AS outs_this_play
    FROM raw.mlb_playbyplay
),
pitcher_game_outs AS (
    SELECT
        rg.game_id,
        rg.game_date,
        po.pitcher_id,
        sum(po.outs_this_play) AS outs
    FROM regular_games rg
    JOIN play_outs po ON po.game_pk = rg.game_pk
    GROUP BY rg.game_id, rg.game_date, po.pitcher_id
),
pitcher_day_outs AS (
    SELECT
        pitcher_id,
        game_date,
        sum(outs) AS outs
    FROM pitcher_game_outs
    GROUP BY pitcher_id, game_date
),
pitcher_day_workload AS (
    SELECT
        pitcher_id,
        game_date,
        SUM(outs) OVER (
            PARTITION BY pitcher_id ORDER BY game_date
            RANGE BETWEEN (%(workload_days)s * INTERVAL '1 day') PRECEDING
                AND INTERVAL '1 day' PRECEDING
        ) AS workload_outs
    FROM pitcher_day_outs
),
starter_stats AS (
    SELECT
        ss.game_id,
        ss.pitcher_id,
        ss.rest_days,
        pdw.workload_outs
    FROM starter_starts ss
    JOIN pitcher_day_workload pdw
        ON pdw.pitcher_id = ss.pitcher_id
        AND pdw.game_date = ss.game_date
)
UPDATE gold.game_feature f
SET
    home_starter_rest_days = hs.rest_days,
    home_starter_outs_7d = hs.workload_outs,
    away_starter_rest_days = ws.rest_days,
    away_starter_outs_7d = ws.workload_outs
FROM starters s
LEFT JOIN starter_stats hs
    ON hs.game_id = s.game_id AND hs.pitcher_id = s.home_starter_id
LEFT JOIN starter_stats ws
    ON ws.game_id = s.game_id AND ws.pitcher_id = s.away_starter_id
WHERE f.game_id = s.game_id AND f.home_starter_rest_days IS NULL
