-- Starter career experience entering a game (PLN-04's "prior MLB PA/IP"
-- half, docs/FEATURE_ADMISSION_QUEUE.md, ADR-085). Career batters-faced
-- and innings-pitched, counted the same way team_starter_retrosheet_
-- update.sql's own pitcher_game_stats CTE already counts a season total
-- (bat_event_fl='T' gate, ADR-034) -- the only difference is the rolling
-- window has NO season partition, spanning a pitcher's whole Retrosheet-
-- covered career (ROWS UNBOUNDED PRECEDING, PARTITION BY pitcher_retro_id
-- only). Entering value: reflects every prior appearance strictly before
-- this game, same point-in-time-safe shape as every other rolling window
-- in this codebase.
--
-- IP is outs_sum / 3.0 (a fractional innings count, e.g. 6.33 for 6 2/3
-- innings) -- same convention as team_starter_retrosheet_update.sql's own
-- FIP denominator.

WITH regular_games AS (
    SELECT g.id AS game_id, g.game_date, g.retro_game_id
    FROM core.game g WHERE g.game_type = 'regular'
),
pitcher_game_stats AS (
    SELECT rg.game_id, rg.game_date, re.resp_pit_id AS pitcher_retro_id,
        count(*) FILTER (WHERE re.bat_event_fl = 'T') AS bf,
        sum(re.event_outs_ct::numeric) AS outs
    FROM regular_games rg
    JOIN raw.retrosheet_gameinfo gi ON gi.gid = rg.retro_game_id AND lower(gi.gametype) = 'regular'
    JOIN raw.retrosheet_event re ON re.game_id = rg.retro_game_id
    GROUP BY rg.game_id, rg.game_date, re.resp_pit_id
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
career AS (
    SELECT game_id, pitcher_retro_id,
        SUM(bf) OVER w_career AS bf_sum,
        SUM(outs) OVER w_career AS outs_sum
    FROM pitcher_game_stats
    WINDOW w_career AS (
        PARTITION BY pitcher_retro_id ORDER BY game_date, game_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
    )
)
UPDATE gold.game_feature f
SET home_starter_career_bf = hc.bf_sum,
    home_starter_career_ip = hc.outs_sum / 3.0,
    away_starter_career_bf = ac.bf_sum,
    away_starter_career_ip = ac.outs_sum / 3.0
FROM starters s
LEFT JOIN career hc ON hc.game_id = s.game_id AND hc.pitcher_retro_id = s.home_starter_retro_id
LEFT JOIN career ac ON ac.game_id = s.game_id AND ac.pitcher_retro_id = s.away_starter_retro_id
WHERE f.game_id = s.game_id;
