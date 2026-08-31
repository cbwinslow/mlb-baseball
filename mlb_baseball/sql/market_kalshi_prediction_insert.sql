INSERT INTO gold.prediction
    (mlb_game_pk, game_instance_key, model_version, home_win_prob, generated_at)
SELECT g.game_pk, f.game_instance_key, %(model_version)s, m.implied_probability, m.observed_at
FROM core.market m
JOIN core.game g ON g.id = m.game_id AND g.home_team_id = m.team_id
JOIN gold.game_feature f ON f.game_id = g.id
WHERE m.source = 'kalshi'
    AND m.implied_probability IS NOT NULL
    AND m.observed_at IS NOT NULL
    AND g.game_pk IS NOT NULL
    AND NOT EXISTS (
        SELECT 1 FROM gold.prediction p
        WHERE p.game_instance_key = f.game_instance_key AND p.model_version = %(model_version)s
    )
