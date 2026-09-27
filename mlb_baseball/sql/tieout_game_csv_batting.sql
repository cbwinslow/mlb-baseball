-- Retrosheet tie-out: per-game totals from Retrosheet's CSV per-player batting.
-- Read-only. Owner: mlb_baseball/tieout_run.py (openspec change raw-source-tieout).
-- 'value' rows only; see tieout_season_csv_batting.sql. Called once per season.
SELECT
    _season AS season,
    gid AS game_id,
    sum(b_pa::integer) AS pa,
    sum(b_k::integer) AS k,
    sum(b_w::integer) AS bb,
    sum(b_hr::integer) AS hr,
    sum(b_r::integer) AS r,
    1 AS g
FROM raw.retrosheet_batting
WHERE stattype = 'value'
    AND _season BETWEEN %(lo)s::text AND %(hi)s::text
GROUP BY _season, gid
ORDER BY gid
