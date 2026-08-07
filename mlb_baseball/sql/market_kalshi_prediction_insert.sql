INSERT INTO gold.prediction (mlb_game_pk, model_version, home_win_prob)
SELECT g.game_pk, %(model_version)s, m.implied_probability
FROM core.market m
JOIN core.game g ON g.id = m.game_id AND g.home_team_id = m.team_id
WHERE m.source = 'kalshi'
    AND m.implied_probability IS NOT NULL
    AND g.game_pk IS NOT NULL
    AND NOT EXISTS (
        SELECT 1 FROM gold.prediction p
        WHERE p.mlb_game_pk = g.game_pk AND p.model_version = %(model_version)s
    )
