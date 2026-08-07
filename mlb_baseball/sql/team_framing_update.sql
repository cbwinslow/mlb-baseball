WITH catcher_team AS (
    SELECT p.id AS player_id, f._season::integer AS season,
        f.rv_tot::numeric AS rv_tot, pw.team_code
    FROM raw.statcast_framing f
    JOIN core.player p ON p.mlbam_id = f.id
    JOIN core.player_war pw
        ON pw.player_id = p.id AND pw.season = f._season::integer AND pw.is_pitcher = false
),
bref_map (bref_code, retro_code) AS (VALUES {values_clause}),
team_season_framing AS (
    SELECT t.id AS team_id, ct.season, sum(ct.rv_tot) AS total_framing
    FROM catcher_team ct
    JOIN bref_map bm ON bm.bref_code = ct.team_code
    JOIN core.team t
        ON t.retro_team_id = bm.retro_code
        AND ct.season BETWEEN t.first_year AND t.last_year
    GROUP BY t.id, ct.season
)
UPDATE gold.game_feature f
SET
    home_framing_prior = hf.total_framing,
    away_framing_prior = af.total_framing
FROM core.game g
LEFT JOIN team_season_framing hf ON hf.team_id = g.home_team_id AND hf.season = g.season - 1
LEFT JOIN team_season_framing af ON af.team_id = g.away_team_id AND af.season = g.season - 1
WHERE f.game_id = g.id
