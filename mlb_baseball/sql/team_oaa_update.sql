WITH team_season_oaa AS (
    SELECT
        CASE o.display_team_name
            WHEN 'D-backs' THEN 'Diamondbacks'
            WHEN 'Rays' THEN 'Devil Rays'
            WHEN 'Guardians' THEN 'Indians'
            ELSE o.display_team_name
        END AS nickname,
        o.year::integer AS season,
        sum(o.fielding_runs_prevented::numeric) AS total_oaa
    FROM raw.statcast_oaa o
    WHERE o.display_team_name != '---'
    GROUP BY 1, 2
),
team_oaa_resolved AS (
    SELECT t.id AS team_id, tso.season, tso.total_oaa
    FROM team_season_oaa tso
    JOIN core.team t
        ON t.nickname = tso.nickname
        AND tso.season BETWEEN t.first_year AND t.last_year
)
UPDATE gold.game_feature f
SET
    home_oaa_prior = ho.total_oaa,
    away_oaa_prior = ao.total_oaa
FROM core.game g
LEFT JOIN team_oaa_resolved ho ON ho.team_id = g.home_team_id AND ho.season = g.season - 1
LEFT JOIN team_oaa_resolved ao ON ao.team_id = g.away_team_id AND ao.season = g.season - 1
WHERE f.game_id = g.id
