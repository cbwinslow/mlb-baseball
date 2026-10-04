-- Retrosheet tie-out: per player-game batting totals from the CSV play-by-play.
-- Read-only. Owner: mlb_baseball/tieout_run.py (openspec change raw-source-tieout).
-- The batter is `batter`. Called once per season.
SELECT
    _season AS season,
    gid AS game_id,
    batter AS player_id,
    sum(pa::integer) AS pa,
    sum(k::integer) AS k,
    sum(walk::integer) AS bb,
    sum(hr::integer) AS hr
FROM raw.retrosheet_plays
WHERE _season BETWEEN %(lo)s::text AND %(hi)s::text
GROUP BY _season, gid, batter
ORDER BY gid, batter
