-- Retrosheet tie-out (core check): season totals from core.play, Retrosheet rows.
-- Read-only. Owner: mlb_baseball/tieout_run.py (openspec change raw-source-tieout).
--
-- core.play carries no batter-event flag (it holds every event), so the batter
-- events are the Chadwick batter-event codes 2, 3 and 14-23, which equal
-- bat_event_fl = 'T' in the event files (checked 2026-09-27 for 2015-2025).
SELECT
    p.season AS season,
    count(*) FILTER (WHERE p.event_code IN
        ('2', '3', '14', '15', '16', '17', '18', '19', '20', '21', '22', '23')) AS pa,
    count(*) FILTER (WHERE p.event_code = '3') AS k,
    count(*) FILTER (WHERE p.event_code IN ('14', '15')) AS bb,
    count(*) FILTER (WHERE p.event_code = '23') AS hr,
    count(DISTINCT p.game_id) AS g
FROM core.play p
WHERE p.source = 'retrosheet'
    AND p.season BETWEEN %(lo)s AND %(hi)s
GROUP BY p.season
ORDER BY p.season
