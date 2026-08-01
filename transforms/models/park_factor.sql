MODEL (
  name gold.park_factor,
  kind INCREMENTAL_BY_TIME_RANGE (
    time_column season_date
  ),
  start '2021-01-01',
  cron '@monthly',
  grain (venue_id, season),
  description '
    Port of mlb_baseball/model/park.py::compute (ADR-035) -- standard
    sabermetric methodology: a venue''s home run-scoring rate (both teams
    combined) divided by the same team''s road run-scoring rate that
    season, scaled to 100 = league average, averaged over a trailing
    3-season window of seasons STRICTLY BEFORE the target season. No
    leakage risk by construction (same as the original): a season''s
    factor only ever looks at prior seasons'' completed games.

    Grain/shape difference from the production version, deliberate for
    this spike: park.py''s UPDATE is driven by whichever (venue_id, season)
    pairs gold.game_feature already needs (a downstream consumer-demand
    query), not by "every venue-season with real home games" -- that
    demand-driven shape only makes sense once gold.game_feature itself
    exists as a wide per-game feature table, which is out of scope for
    this spike (we ported 3 standalone transforms, not the whole feature
    pipeline). This model instead computes eagerly for every (venue,
    season) that had at least one completed regular-season home game --
    a proper dimensional table on its own, joinable into a game-level
    feature table the same way gold.game_feature''s own UPDATE...FROM does.
    Tie-out (see transforms/README.md) confirms the actual NUMBERS match
    production exactly for this shape difference to be a non-issue.

    Incremental by season_date (synthesized as Jan 1 of the season) -- a
    real SQLMesh selling point exercised here: adding a new season''s worth
    of core.game data only recomputes THAT season''s park factors, not a
    full truncate-rebuild of the whole table the way conform.py/park.py
    both do today (park.py''s own UPDATE re-touches every venue-season
    gold.game_feature asks for, every run).
  ',
  audits (
    unique_combination_of_columns(columns := (venue_id, season)),
    not_null(columns := (venue_id, season)),
    park_factor_plausible_range()
  )
);

WITH home_splits AS (
    SELECT home_team_id AS team_id, season, venue_id,
        count(*) AS games, sum(home_score + away_score) AS runs
    FROM core.game
    WHERE game_type = 'regular' AND home_score IS NOT NULL
        AND away_score IS NOT NULL AND venue_id IS NOT NULL
    GROUP BY home_team_id, season, venue_id
),
road_splits AS (
    SELECT away_team_id AS team_id, season,
        count(*) AS games, sum(home_score + away_score) AS runs
    FROM core.game
    WHERE game_type = 'regular' AND home_score IS NOT NULL AND away_score IS NOT NULL
    GROUP BY away_team_id, season
),
team_season_pf AS (
    SELECT h.team_id, h.season, h.venue_id,
        (h.runs::numeric / NULLIF(h.games, 0)) AS home_rate,
        (r.runs::numeric / NULLIF(r.games, 0)) AS road_rate
    FROM home_splits h
    JOIN road_splits r ON r.team_id = h.team_id AND r.season = h.season
),
-- Target grain for THIS model: every (venue, season) with real completed
-- home games -- see model docstring for how/why this differs from
-- production's gold.game_feature-demand-driven shape.
venue_seasons AS (
    SELECT DISTINCT venue_id, season FROM home_splits
)
SELECT
    n.venue_id,
    n.season,
    make_date(n.season, 1, 1) AS season_date,
    avg(100.0 * b.home_rate / NULLIF(b.road_rate, 0)) AS park_factor
FROM venue_seasons n
JOIN team_season_pf b ON b.venue_id = n.venue_id
    AND b.season BETWEEN n.season - 3 AND n.season - 1
WHERE make_date(n.season, 1, 1) BETWEEN @start_ds AND @end_ds
GROUP BY n.venue_id, n.season
