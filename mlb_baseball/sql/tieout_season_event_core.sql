-- Retrosheet tie-out (core check): season totals from the event files, limited
-- to games that exist in core.game.
-- Read-only. Owner: mlb_baseball/tieout_run.py (openspec change raw-source-tieout).
--
-- conform's _build_plays inner-joins events to core.game (conform.py:1094), so
-- this is what core.play can be expected to hold. Event games with no core.game
-- row are reported separately (tieout_event_games_not_in_core.sql). Same fact
-- definitions and de-duplication as tieout_season_event.sql.
WITH ev AS (
    SELECT DISTINCT ON (game_id, event_id)
        game_id, event_id, event_cd, bat_event_fl, _season
    FROM raw.retrosheet_event
    WHERE _season::integer BETWEEN %(lo)s AND %(hi)s
    ORDER BY game_id, event_id, _scope
)
SELECT
    ev._season AS season,
    count(*) FILTER (WHERE ev.bat_event_fl = 'T') AS pa,
    count(*) FILTER (WHERE ev.bat_event_fl = 'T' AND ev.event_cd = '3') AS k,
    count(*) FILTER (WHERE ev.bat_event_fl = 'T' AND ev.event_cd IN ('14', '15')) AS bb,
    count(*) FILTER (WHERE ev.bat_event_fl = 'T' AND ev.event_cd = '23') AS hr,
    count(DISTINCT ev.game_id) AS g
FROM ev
JOIN core.game cg ON cg.retro_game_id = ev.game_id
GROUP BY ev._season
ORDER BY ev._season
