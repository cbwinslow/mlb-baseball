WITH team_season_speed AS (
    SELECT
        s.team_id::integer AS mlb_team_id,
        s._season::integer AS season,
        sum(s.sprint_speed::numeric * s.competitive_runs::numeric)
            / sum(s.competitive_runs::numeric) AS weighted_speed
    FROM raw.statcast_sprint_speed s
    WHERE s.competitive_runs::numeric > 0
    GROUP BY 1, 2
),
team_speed_resolved AS (
    SELECT t.id AS team_id, tss.season, tss.weighted_speed
    FROM team_season_speed tss
    JOIN core.team t
        ON t.mlb_team_id = tss.mlb_team_id
        AND tss.season BETWEEN t.first_year AND t.last_year
)
UPDATE gold.game_feature f
SET
    home_speed_prior = hs.weighted_speed,
    away_speed_prior = aws.weighted_speed
FROM core.game g
LEFT JOIN team_speed_resolved hs ON hs.team_id = g.home_team_id AND hs.season = g.season - 1
LEFT JOIN team_speed_resolved aws ON aws.team_id = g.away_team_id AND aws.season = g.season - 1
WHERE f.game_id = g.id
