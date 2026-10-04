-- Retrosheet tie-out (core check): event games that have no core.game row, so
-- conform's inner join keeps them out of core.play (audit finding G7).
-- Read-only. Owner: mlb_baseball/tieout_run.py (openspec change raw-source-tieout).
-- Reported, not a failure: the known cases are event games Retrosheet publishes
-- without a game info row (for example an Oct-1900 Pittsburgh series). The count
-- per season is here so a change in it is visible.
SELECT
    ev._season AS season,
    count(DISTINCT ev.game_id) AS games,
    min(ev.game_id) AS example_game
FROM raw.retrosheet_event ev
LEFT JOIN core.game cg ON cg.retro_game_id = ev.game_id
WHERE ev._season::integer BETWEEN %(lo)s AND %(hi)s
    AND cg.id IS NULL
GROUP BY ev._season
ORDER BY ev._season
