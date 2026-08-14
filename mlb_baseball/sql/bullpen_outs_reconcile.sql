-- Reconcile relief + starter outs vs team's total outs pitched
WITH regular_games AS (
    SELECT g.id AS game_id, g.retro_game_id, g.home_team_id, g.away_team_id
    FROM core.game g WHERE g.game_type = 'regular'
),
starters AS (
    SELECT rg.game_id,
        max(re.resp_pit_id) FILTER (WHERE re.bat_home_id = '0') AS home_sp,
        max(re.resp_pit_id) FILTER (WHERE re.bat_home_id = '1') AS away_sp
    FROM regular_games rg
    JOIN raw.retrosheet_gameinfo gi
        ON gi.gid = rg.retro_game_id AND lower(gi.gametype) = 'regular'
    JOIN raw.retrosheet_event re ON re.game_id = rg.retro_game_id
    WHERE re.resp_pit_start_fl = 'T'
    GROUP BY rg.game_id
),
team_pitcher_outs AS (
    SELECT rg.game_id,
        CASE WHEN re.bat_home_id = '0'
            THEN rg.home_team_id ELSE rg.away_team_id END AS team_id,
        re.resp_pit_id AS pitcher_retro_id,
        sum(re.event_outs_ct::numeric) AS outs
    FROM regular_games rg
    JOIN raw.retrosheet_gameinfo gi
        ON gi.gid = rg.retro_game_id AND lower(gi.gametype) = 'regular'
    JOIN raw.retrosheet_event re ON re.game_id = rg.retro_game_id
    GROUP BY rg.game_id, rg.home_team_id, rg.away_team_id,
        re.bat_home_id, re.resp_pit_id
),
per_team_game AS (
    SELECT tpo.game_id, tpo.team_id, sum(tpo.outs) AS total_outs,
        sum(tpo.outs) FILTER (WHERE tpo.pitcher_retro_id = CASE
            WHEN tpo.team_id = rg.home_team_id THEN s.home_sp ELSE s.away_sp END
        ) AS starter_outs,
        sum(tpo.outs) FILTER (WHERE tpo.pitcher_retro_id IS DISTINCT FROM CASE
            WHEN tpo.team_id = rg.home_team_id THEN s.home_sp ELSE s.away_sp END
        ) AS relief_outs
    FROM team_pitcher_outs tpo
    JOIN regular_games rg ON rg.game_id = tpo.game_id
    JOIN starters s ON s.game_id = tpo.game_id
    GROUP BY tpo.game_id, tpo.team_id
)
SELECT game_id || '-' || team_id, total_outs,
    COALESCE(starter_outs, 0) + COALESCE(relief_outs, 0)
FROM per_team_game;
