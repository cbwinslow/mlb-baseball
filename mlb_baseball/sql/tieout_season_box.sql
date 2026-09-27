-- Retrosheet tie-out: season totals from the box scores (1871-1961 only).
-- Read-only. Owner: mlb_baseball/tieout_run.py (openspec change raw-source-tieout).
--
-- One copy per game_id (raw.retrosheet_box_game holds 5 game_ids twice, across
-- archives): DISTINCT ON ... ORDER BY _scope, the same rule as the event table.
-- Batting is summed over the kept game copies only.
WITH games AS (
    SELECT DISTINCT ON (game_id) game_id, _season, _scope,
        linescore_away_runs, linescore_home_runs
    FROM raw.retrosheet_box_game
    WHERE _season BETWEEN %(lo)s::text AND %(hi)s::text
    ORDER BY game_id, _scope
),
batting AS (
    SELECT g._season,
        sum(b.hr::integer) AS hr,
        sum(b.so::integer) AS k,
        sum(b.bb::integer) AS bb
    FROM games g
    JOIN raw.retrosheet_box_batting b ON b.game_id = g.game_id AND b._scope = g._scope
    GROUP BY g._season
),
runs AS (
    SELECT _season,
        sum(linescore_away_runs::integer + linescore_home_runs::integer) AS r,
        count(*) AS g
    FROM games
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
