-- Retrosheet tie-out (core check): per-game runs from core.game, Retrosheet rows.
-- Read-only. Owner: mlb_baseball/tieout_run.py (openspec change raw-source-tieout).
SELECT
    season,
    retro_game_id AS game_id,
    coalesce(away_score, 0) + coalesce(home_score, 0) AS r,
    1 AS g
FROM core.game
WHERE retro_game_id IS NOT NULL
    AND season BETWEEN %(lo)s AND %(hi)s
ORDER BY retro_game_id
