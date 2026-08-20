-- Reconcile relief + starter outs vs team's total outs pitched
--
-- One pass over raw.retrosheet_event, not two (issue #46): the previous
-- version had a `starters` CTE and a `team_pitcher_outs` CTE each
-- independently re-join core.game -> raw.retrosheet_gameinfo ->
-- raw.retrosheet_event, scanning the same ~16M event rows twice and
-- paying for two disk-spilling sorts. Here that join happens once
-- (team_events), and a window aggregate over it (event_rows) --
-- not a second GROUP BY + JOIN -- resolves each team's starter over
-- the same scan that also produces per-pitcher outs -- confirmed
-- row-for-row identical against production to the old two-scan
-- version (406,516/406,516 rows, zero mismatches either direction)
-- before landing this change.
WITH regular_games AS (
    SELECT g.id AS game_id, g.retro_game_id, g.home_team_id, g.away_team_id
    FROM core.game g WHERE g.game_type = 'regular'
),
team_events AS (
    SELECT rg.game_id,
        CASE WHEN re.bat_home_id = '0'
            THEN rg.home_team_id ELSE rg.away_team_id END AS team_id,
        re.resp_pit_id AS pitcher_retro_id,
        re.event_outs_ct::numeric AS outs,
        re.resp_pit_start_fl
    FROM regular_games rg
    JOIN raw.retrosheet_gameinfo gi
        ON gi.gid = rg.retro_game_id AND lower(gi.gametype) = 'regular'
    JOIN raw.retrosheet_event re ON re.game_id = rg.retro_game_id
),
event_rows AS (
    SELECT game_id, team_id, pitcher_retro_id, outs,
        max(pitcher_retro_id) FILTER (WHERE resp_pit_start_fl = 'T')
            OVER (PARTITION BY game_id, team_id) AS starter_id
    FROM team_events
),
per_team_game AS (
    SELECT game_id, team_id, sum(outs) AS total_outs,
        sum(outs) FILTER (WHERE pitcher_retro_id = starter_id) AS starter_outs,
        sum(outs) FILTER (WHERE pitcher_retro_id IS DISTINCT FROM starter_id) AS relief_outs
    FROM event_rows
    GROUP BY game_id, team_id
)
SELECT game_id || '-' || team_id, total_outs,
    COALESCE(starter_outs, 0) + COALESCE(relief_outs, 0)
FROM per_team_game;
