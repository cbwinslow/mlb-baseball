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
--
-- Seasons before 1910 are excluded: this connector's own documented coverage
-- (retrosheet_event.py's module docstring) is "full play-by-play 1910-2025";
-- confirmed by the first full-history run (task 4.2, results-history.md) --
-- every row before 1910 has _group 'postseason' or 'negro_league', never
-- 'pbp' (zero exceptions), so pre-1910 seasons only ever hold a handful of
-- World Series/Negro-League games, not a real season. Comparing that scant
-- total against the CSV/game-log products' comprehensive regular-season
-- totals (which do cover back to 1898) is comparing different scopes, not a
-- real disagreement -- the same kind of coverage boundary as the box-score
-- product's 1871-1961 range.
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
    count(*) FILTER (WHERE bat_event_fl = 'T') AS pa,
    count(*) FILTER (WHERE bat_event_fl = 'T' AND event_cd = '3') AS k,
    count(*) FILTER (WHERE bat_event_fl = 'T' AND event_cd IN ('14', '15')) AS bb,
    count(*) FILTER (WHERE bat_event_fl = 'T' AND event_cd = '23') AS hr,
    sum(event_runs_ct::integer) AS r,
    count(DISTINCT game_id) AS g
FROM ev
GROUP BY _season
ORDER BY _season
