-- Retrosheet tie-out (core check): per-game totals from core.play, Retrosheet
-- rows. See tieout_season_core_play.sql. Called once per season.
-- Read-only. Owner: mlb_baseball/tieout_run.py (openspec change raw-source-tieout).
SELECT
    p.season AS season,
    cg.retro_game_id AS game_id,
    count(*) FILTER (WHERE p.event_code IN
        ('2', '3', '14', '15', '16', '17', '18', '19', '20', '21', '22', '23')) AS pa,
    count(*) FILTER (WHERE p.event_code = '3') AS k,
    count(*) FILTER (WHERE p.event_code IN ('14', '15')) AS bb,
    count(*) FILTER (WHERE p.event_code = '23') AS hr,
    1 AS g
FROM core.play p
JOIN core.game cg ON cg.id = p.game_id
WHERE p.source = 'retrosheet'
    AND p.season BETWEEN %(lo)s AND %(hi)s
GROUP BY p.season, cg.retro_game_id
ORDER BY cg.retro_game_id
