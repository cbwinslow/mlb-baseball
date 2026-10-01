-- Retrosheet tie-out: per-game totals from the Chadwick-parsed event files.
-- Read-only. Owner: mlb_baseball/tieout_run.py (openspec change raw-source-tieout).
--
-- Same fact definitions, de-duplication and pre-1910 exclusion as
-- tieout_season_event.sql (see it for the checked definitions, register
-- entry E2, and why 1910 is the real coverage start). Called once per season.
WITH ev AS (
    SELECT DISTINCT ON (game_id, event_id)
        game_id, event_id, event_cd, bat_event_fl, event_runs_ct, _season
    FROM raw.retrosheet_event
    WHERE _season::integer BETWEEN %(lo)s AND %(hi)s
        AND _season::integer >= 1910
    ORDER BY game_id, event_id, _scope
)
SELECT
    _season AS season,
    game_id,
    count(*) FILTER (WHERE bat_event_fl = 'T') AS pa,
    count(*) FILTER (WHERE bat_event_fl = 'T' AND event_cd = '3') AS k,
    count(*) FILTER (WHERE bat_event_fl = 'T' AND event_cd IN ('14', '15')) AS bb,
    count(*) FILTER (WHERE bat_event_fl = 'T' AND event_cd = '23') AS hr,
    sum(event_runs_ct::integer) AS r,
    1 AS g
FROM ev
GROUP BY _season, game_id
ORDER BY game_id
