-- Retrosheet tie-out (core check): season totals from core.game, Retrosheet rows.
-- Read-only. Owner: mlb_baseball/tieout_run.py (openspec change raw-source-tieout).
-- A NULL score counts as 0 here so a score that failed to convert shows up as a
-- difference against game info instead of failing the query.
SELECT
    season,
    sum(coalesce(away_score, 0) + coalesce(home_score, 0)) AS r,
    count(*) AS g
FROM core.game
WHERE retro_game_id IS NOT NULL
    AND season BETWEEN %(lo)s AND %(hi)s
GROUP BY season
ORDER BY season
