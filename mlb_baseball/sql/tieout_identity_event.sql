-- Retrosheet tie-out: event batter and pitcher ids that resolve to no roster row
-- and no all-players row in the same season.
-- Read-only. Owner: mlb_baseball/tieout_run.py (openspec change raw-source-tieout).
-- One row per (season, role, id) with the number of events and one example game.
WITH ids AS (
    SELECT _season, 'batter' AS role, bat_id AS id, game_id
    FROM raw.retrosheet_event
    WHERE _season::integer BETWEEN %(lo)s AND %(hi)s
    UNION ALL
    SELECT _season, 'pitcher', pit_id, game_id
    FROM raw.retrosheet_event
    WHERE _season::integer BETWEEN %(lo)s AND %(hi)s
)
SELECT i._season AS season, i.role, i.id, count(*) AS events, min(i.game_id) AS example_game
FROM ids i
WHERE NOT EXISTS (
        SELECT 1 FROM raw.retrosheet_roster r
        WHERE r.player_id = i.id AND r._season = i._season)
    AND NOT EXISTS (
        SELECT 1 FROM raw.retrosheet_allplayers a
        WHERE a.id = i.id AND a._season = i._season)
GROUP BY i._season, i.role, i.id
ORDER BY i._season, i.role, i.id
