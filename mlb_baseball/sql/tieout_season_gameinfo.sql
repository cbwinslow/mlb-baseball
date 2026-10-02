-- Retrosheet tie-out: season totals from the CSV product's game info.
-- Read-only. Owner: mlb_baseball/tieout_run.py (openspec change raw-source-tieout).
--
-- All game types (regular season, postseason, all-star): 2019 has 2,467 games,
-- 2,429 of them regular season. r is both teams' runs.
SELECT
    _season AS season,
    sum(vruns::integer + hruns::integer) AS r,
    count(*) AS g
FROM raw.retrosheet_gameinfo
WHERE _season BETWEEN %(lo)s::text AND %(hi)s::text
GROUP BY _season
ORDER BY _season
