-- Retrosheet tie-out: per-game totals from Retrosheet's CSV play-by-play.
-- Read-only. Owner: mlb_baseball/tieout_run.py (openspec change raw-source-tieout).
-- Same flags as tieout_season_csv_plays.sql. Called once per season.
SELECT
    _season AS season,
    gid AS game_id,
    sum(pa::integer) AS pa,
    sum(k::integer) AS k,
    sum(walk::integer) AS bb,
    sum(hr::integer) AS hr,
    sum(runs::integer) AS r,
    1 AS g
FROM raw.retrosheet_plays
WHERE _season BETWEEN %(lo)s::text AND %(hi)s::text
GROUP BY _season, gid
ORDER BY gid
