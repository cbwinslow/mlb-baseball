-- Retrosheet tie-out: season totals from the Chadwick-parsed event files.
-- Read-only. Owner: mlb_baseball/tieout_run.py (openspec change raw-source-tieout).
--
-- One copy of each (game_id, event_id), chosen the same way conform's
-- _build_plays chooses it (DISTINCT ON ... ORDER BY _scope), so the 1,872
-- Negro League games published in two archives are counted once (register E2).
-- Fact definitions, checked against Retrosheet's CSV batting for 2019:
--   pa  batter events            = bat_event_fl 'T'
--   k   strikeouts               = event_cd 3
--   bb  walks incl. intentional  = event_cd 14 + 15
--   hr  home runs                = event_cd 23
--   r   runs scored              = sum of event_runs_ct
--   g   games                    = distinct game_id
-- The _season filter is written to use the integer expression index.
WITH ev AS (
    SELECT DISTINCT ON (game_id, event_id)
        game_id, event_id, event_cd, bat_event_fl, event_runs_ct, _season
    FROM raw.retrosheet_event
    WHERE _season::integer BETWEEN %(lo)s AND %(hi)s
    ORDER BY game_id, event_id, _scope
)
SELECT
    _season AS season,
    count(*) FILTER (WHERE bat_event_fl = 'T') AS pa,
    count(*) FILTER (WHERE bat_event_fl = 'T' AND event_cd = '3') AS k,
    count(*) FILTER (WHERE bat_event_fl = 'T' AND event_cd IN ('14', '15')) AS bb,
    count(*) FILTER (WHERE bat_event_fl = 'T' AND event_cd = '23') AS hr,
    sum(event_runs_ct::integer) AS r,
    count(DISTINCT game_id) AS g
FROM ev
GROUP BY _season
ORDER BY _season
