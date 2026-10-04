-- Retrosheet tie-out: per-game runs from the CSV product's game info.
-- Read-only. Owner: mlb_baseball/tieout_run.py (openspec change raw-source-tieout).
SELECT
    _season AS season,
    gid AS game_id,
    vruns::integer + hruns::integer AS r,
    1 AS g
FROM raw.retrosheet_gameinfo
WHERE _season BETWEEN %(lo)s::text AND %(hi)s::text
ORDER BY gid
