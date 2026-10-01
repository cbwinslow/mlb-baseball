-- Retrosheet tie-out: season totals from the box scores (1871-1961 only).
-- Read-only. Owner: mlb_baseball/tieout_run.py (openspec change raw-source-tieout).
--
-- One copy per game_id (raw.retrosheet_box_game holds 5 game_ids twice, across
-- archives): DISTINCT ON ... ORDER BY _scope, the same rule as the event table.
-- Batting is summed over the kept game copies only.
--
-- '-1' in hr/so/bb is a real Retrosheet sentinel for "not recorded" (a box
-- score whose source didn't report that stat per batter), not a literal
-- negative count -- found by the first full-history run (task 4.2,
-- results-history.md) when a season's k total came out negative. It is
-- common (about a third of all raw.retrosheet_box_batting rows for `so`
-- alone, checked with no exceptions on the value itself: it is always
-- exactly '-1', never some other negative number). A whole season is
-- excluded here (not
-- comparable via box) if even one of its batters has a '-1' in any of the
-- three columns -- the same "not comparable, not a total silently short by
-- an unknown amount" choice as tieout_season_gamelog.sql's NULL handling, and
-- the reason r/g are excluded for that season too, even though the score
-- columns are never sentinel-valued: keeping hr/k/bb and r/g scoped to the
-- exact same set of games avoids a season row that mixes a comprehensive
-- game count with a partial batting total.
WITH games AS (
    SELECT DISTINCT ON (game_id) game_id, _season, _scope,
        linescore_away_runs, linescore_home_runs
    FROM raw.retrosheet_box_game
    WHERE _season BETWEEN %(lo)s::text AND %(hi)s::text
    ORDER BY game_id, _scope
),
season_has_a_sentinel AS (
    SELECT DISTINCT g._season
    FROM games g
    JOIN raw.retrosheet_box_batting b ON b.game_id = g.game_id AND b._scope = g._scope
    WHERE b.hr = '-1' OR b.so = '-1' OR b.bb = '-1'
),
batting AS (
    SELECT g._season,
        sum(b.hr::integer) AS hr,
        sum(b.so::integer) AS k,
        sum(b.bb::integer) AS bb
    FROM games g
    JOIN raw.retrosheet_box_batting b ON b.game_id = g.game_id AND b._scope = g._scope
    WHERE g._season NOT IN (SELECT _season FROM season_has_a_sentinel)
    GROUP BY g._season
),
runs AS (
    SELECT _season,
        sum(linescore_away_runs::integer + linescore_home_runs::integer) AS r,
        count(*) AS g
    FROM games
    WHERE _season NOT IN (SELECT _season FROM season_has_a_sentinel)
    GROUP BY _season
)
SELECT runs._season AS season,
    coalesce(batting.hr, 0) AS hr,
    coalesce(batting.k, 0) AS k,
    coalesce(batting.bb, 0) AS bb,
    runs.r AS r,
    runs.g AS g
FROM runs
LEFT JOIN batting ON batting._season = runs._season
ORDER BY runs._season
