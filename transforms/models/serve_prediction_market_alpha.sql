MODEL (
  name serve.prediction_market_alpha,
  kind FULL,
  cron '@daily',
  grain (game_instance_key, market_source)
);

SELECT
    f.game_instance_key,
    f.game_date,
    ht.retro_team_id AS home_team,
    at.retro_team_id AS away_team,
    m.source AS market_source,
    m.implied_probability AS market_home_prob,
    COALESCE(p_gbm.home_win_prob, p_elo.home_win_prob, p_log5.home_win_prob) AS model_home_win_prob,
    ROUND(
        COALESCE(p_gbm.home_win_prob, p_elo.home_win_prob, p_log5.home_win_prob) - m.implied_probability,
        4
    ) AS home_edge_alpha,
    CASE
        WHEN (COALESCE(p_gbm.home_win_prob, p_elo.home_win_prob, p_log5.home_win_prob) - m.implied_probability) >= 0.025 THEN 'BUY_HOME_YES'
        WHEN (m.implied_probability - COALESCE(p_gbm.home_win_prob, p_elo.home_win_prob, p_log5.home_win_prob)) >= 0.025 THEN 'BUY_AWAY_YES'
        ELSE 'PASS'
    END AS recommendation
FROM gold.game_feature f
JOIN core.market m ON m.game_id = f.game_id AND m.team_id = f.home_team_id
LEFT JOIN core.team ht ON ht.id = f.home_team_id
LEFT JOIN core.team at ON at.id = f.away_team_id
LEFT JOIN gold.prediction p_gbm ON p_gbm.game_instance_key = f.game_instance_key AND p_gbm.model_version = 'gbm-v1'
LEFT JOIN gold.prediction p_elo ON p_elo.game_instance_key = f.game_instance_key AND p_elo.model_version = 'elo-v1'
LEFT JOIN gold.prediction p_log5 ON p_log5.game_instance_key = f.game_instance_key AND p_log5.model_version = 'log5-v1';
