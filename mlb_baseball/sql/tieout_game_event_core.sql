-- Retrosheet tie-out (core check): per-game totals from the event files, limited
-- to games that exist in core.game. See tieout_season_event_core.sql.
-- Read-only. Owner: mlb_baseball/tieout_run.py (openspec change raw-source-tieout).
WITH ev AS (
    SELECT DISTINCT ON (game_id, event_id)
        game_id, event_id, event_cd, bat_event_fl, _season
    FROM raw.retrosheet_event
    WHERE _season::integer BETWEEN %(lo)s AND %(hi)s
    ORDER BY game_id, event_id, _scope
)
SELECT
    ev._season AS season,
    ev.game_id,
    count(*) FILTER (WHERE ev.bat_event_fl = 'T') AS pa,
    count(*) FILTER (WHERE ev.bat_event_fl = 'T' AND ev.event_cd = '3') AS k,
    count(*) FILTER (WHERE ev.bat_event_fl = 'T' AND ev.event_cd IN ('14', '15')) AS bb,
    count(*) FILTER (WHERE ev.bat_event_fl = 'T' AND ev.event_cd = '23') AS hr,
    1 AS g
FROM ev
JOIN core.game cg ON cg.retro_game_id = ev.game_id
GROUP BY ev._season, ev.game_id
ORDER BY ev.game_id
