WITH regular_games AS (
    SELECT g.id AS game_id, g.season, g.game_date, g.retro_game_id
    FROM core.game g
    WHERE g.game_type = 'regular'
),
starters AS (
    SELECT rg.game_id, rg.game_date,
        max(re.resp_pit_id) FILTER (WHERE re.bat_home_id = '0') AS home_starter_retro_id,
        max(re.resp_pit_id) FILTER (WHERE re.bat_home_id = '1') AS away_starter_retro_id
    FROM regular_games rg
    JOIN raw.retrosheet_gameinfo gi ON gi.gid = rg.retro_game_id AND lower(gi.gametype) = 'regular'
    JOIN raw.retrosheet_event re ON re.game_id = rg.retro_game_id
    WHERE re.resp_pit_start_fl = 'T'
    GROUP BY rg.game_id, rg.game_date
),
starter_starts AS (
    SELECT
        rg.game_id,
        rg.game_date,
        re.resp_pit_id AS pitcher_retro_id,
        rg.game_date - LAG(rg.game_date) OVER (
            PARTITION BY re.resp_pit_id ORDER BY rg.game_date, rg.game_id
        ) AS rest_days
    FROM regular_games rg
    JOIN raw.retrosheet_gameinfo gi ON gi.gid = rg.retro_game_id AND lower(gi.gametype) = 'regular'
    JOIN raw.retrosheet_event re ON re.game_id = rg.retro_game_id
    WHERE re.resp_pit_start_fl = 'T'
    GROUP BY rg.game_id, rg.game_date, re.resp_pit_id
),
pitcher_game_outs AS (
    SELECT
        rg.game_id,
        rg.game_date,
        re.resp_pit_id AS pitcher_retro_id,
        sum(re.event_outs_ct::numeric) AS outs
    FROM regular_games rg
    JOIN raw.retrosheet_gameinfo gi ON gi.gid = rg.retro_game_id AND lower(gi.gametype) = 'regular'
    JOIN raw.retrosheet_event re ON re.game_id = rg.retro_game_id
    GROUP BY rg.game_id, rg.game_date, re.resp_pit_id
),
pitcher_day_outs AS (
    SELECT
        pitcher_retro_id,
        game_date,
        sum(outs) AS outs
    FROM pitcher_game_outs
    GROUP BY pitcher_retro_id, game_date
),
pitcher_day_workload AS (
    SELECT
        pitcher_retro_id,
        game_date,
        SUM(outs) OVER (
            PARTITION BY pitcher_retro_id ORDER BY game_date
            RANGE BETWEEN (%(workload_days)s * INTERVAL '1 day') PRECEDING
                AND INTERVAL '1 day' PRECEDING
        ) AS workload_outs
    FROM pitcher_day_outs
),
starter_stats AS (
    SELECT
        ss.game_id,
        ss.pitcher_retro_id,
        ss.rest_days,
        pdw.workload_outs
    FROM starter_starts ss
    JOIN pitcher_day_workload pdw
        ON pdw.pitcher_retro_id = ss.pitcher_retro_id
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
    ON hs.game_id = s.game_id AND hs.pitcher_retro_id = s.home_starter_retro_id
LEFT JOIN starter_stats ws
    ON ws.game_id = s.game_id AND ws.pitcher_retro_id = s.away_starter_retro_id
WHERE f.game_id = s.game_id
