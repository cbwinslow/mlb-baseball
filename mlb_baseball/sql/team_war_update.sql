WITH team_war AS (
    SELECT team_code, season, sum(war) AS total_war
    FROM core.player_war
    GROUP BY team_code, season
),
bref_map (bref_code, retro_code) AS (VALUES {values_clause}),
team_war_resolved AS (
    SELECT t.id AS team_id, tw.season, tw.total_war
    FROM team_war tw
    JOIN bref_map bm ON bm.bref_code = tw.team_code
    JOIN core.team t ON t.retro_team_id = bm.retro_code
        AND tw.season BETWEEN t.first_year AND t.last_year
)
UPDATE gold.game_feature f
SET
    home_war_prior = hw.total_war,
    away_war_prior = aw.total_war
FROM core.game g
LEFT JOIN team_war_resolved hw ON hw.team_id = g.home_team_id AND hw.season = g.season - 1
LEFT JOIN team_war_resolved aw ON aw.team_id = g.away_team_id AND aw.season = g.season - 1
WHERE f.game_id = g.id
