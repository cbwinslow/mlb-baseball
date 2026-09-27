-- Retrosheet tie-out: per player-game batting totals from the event files.
-- Read-only. Owner: mlb_baseball/tieout_run.py (openspec change raw-source-tieout).
-- The batter is bat_id. Runs scored are not attributed to a batter in the event
-- table, so r is not a player-game fact for this source. Called once per season.
WITH ev AS (
    SELECT DISTINCT ON (game_id, event_id)
        game_id, event_id, event_cd, bat_event_fl, bat_id, _season
    FROM raw.retrosheet_event
    WHERE _season::integer BETWEEN %(lo)s AND %(hi)s
    ORDER BY game_id, event_id, _scope
)
SELECT
    _season AS season,
    game_id,
    bat_id AS player_id,
    count(*) FILTER (WHERE bat_event_fl = 'T') AS pa,
    count(*) FILTER (WHERE bat_event_fl = 'T' AND event_cd = '3') AS k,
    count(*) FILTER (WHERE bat_event_fl = 'T' AND event_cd IN ('14', '15')) AS bb,
    count(*) FILTER (WHERE bat_event_fl = 'T' AND event_cd = '23') AS hr
FROM ev
GROUP BY _season, game_id, bat_id
ORDER BY game_id, bat_id
