-- Retrosheet tie-out: per-game totals from the box scores (1871-1961 only).
-- Read-only. Owner: mlb_baseball/tieout_run.py (openspec change raw-source-tieout).
-- One copy per game_id, chosen as in tieout_season_box.sql. Called once per season.
-- '-1' sentinel exclusion as in tieout_season_box.sql, at game grain: a game
-- is excluded entirely (not comparable via box) if any of its batters has a
-- '-1' in hr/so/bb.
WITH games AS (
    SELECT DISTINCT ON (game_id) game_id, _season, _scope,
        linescore_away_runs, linescore_home_runs
    FROM raw.retrosheet_box_game
    WHERE _season BETWEEN %(lo)s::text AND %(hi)s::text
    ORDER BY game_id, _scope
),
games_with_a_sentinel AS (
    SELECT DISTINCT g.game_id
    FROM games g
    JOIN raw.retrosheet_box_batting b ON b.game_id = g.game_id AND b._scope = g._scope
    WHERE b.hr = '-1' OR b.so = '-1' OR b.bb = '-1'
),
clean_games AS (
    SELECT * FROM games WHERE game_id NOT IN (SELECT game_id FROM games_with_a_sentinel)
),
batting AS (
    SELECT g.game_id,
        sum(b.hr::integer) AS hr,
        sum(b.so::integer) AS k,
        sum(b.bb::integer) AS bb
    FROM clean_games g
    JOIN raw.retrosheet_box_batting b ON b.game_id = g.game_id AND b._scope = g._scope
    GROUP BY g.game_id
)
SELECT g._season AS season,
    g.game_id,
    coalesce(batting.hr, 0) AS hr,
    coalesce(batting.k, 0) AS k,
    coalesce(batting.bb, 0) AS bb,
    g.linescore_away_runs::integer + g.linescore_home_runs::integer AS r,
    1 AS g
FROM clean_games g
LEFT JOIN batting ON batting.game_id = g.game_id
ORDER BY g.game_id
