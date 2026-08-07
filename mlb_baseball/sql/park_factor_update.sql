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
venue_seasons_needed AS (
    SELECT DISTINCT venue_id, season FROM gold.game_feature WHERE venue_id IS NOT NULL
),
venue_trailing AS (
    SELECT n.venue_id, n.season AS target_season,
        avg(100.0 * b.home_rate / NULLIF(b.road_rate, 0)) AS park_factor
    FROM venue_seasons_needed n
    JOIN team_season_pf b ON b.venue_id = n.venue_id
        AND b.season BETWEEN n.season - %(trailing_seasons)s AND n.season - 1
    GROUP BY n.venue_id, n.season
)
UPDATE gold.game_feature f
SET park_factor = v.park_factor
FROM venue_trailing v
WHERE f.venue_id = v.venue_id AND f.season = v.target_season
