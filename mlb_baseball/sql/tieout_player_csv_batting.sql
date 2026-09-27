-- Retrosheet tie-out: per player-game batting from Retrosheet's CSV batting.
-- Read-only. Owner: mlb_baseball/tieout_run.py (openspec change raw-source-tieout).
-- 'value' rows only (see tieout_season_csv_batting.sql). Rows are summed per
-- (game, player) in case a player has more than one lineup slot in a game.
SELECT
    _season AS season,
    gid AS game_id,
    id AS player_id,
    sum(b_pa::integer) AS pa,
    sum(b_k::integer) AS k,
    sum(b_w::integer) AS bb,
    sum(b_hr::integer) AS hr,
    sum(b_r::integer) AS r
FROM raw.retrosheet_batting
WHERE stattype = 'value'
    AND _season BETWEEN %(lo)s::text AND %(hi)s::text
GROUP BY _season, gid, id
ORDER BY gid, id
