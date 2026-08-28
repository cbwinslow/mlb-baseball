-- Health check: verify leverage index and RE24 features in gold.game_feature
-- starter avg LI, bullpen avg LI must be >= 0.0 when populated

SELECT
    count(*) FILTER (WHERE home_starter_avg_li IS NOT NULL AND home_starter_avg_li < 0.0) AS invalid_h_sp_li,
    count(*) FILTER (WHERE away_starter_avg_li IS NOT NULL AND away_starter_avg_li < 0.0) AS invalid_a_sp_li,
    count(*) FILTER (WHERE home_bullpen_avg_li IS NOT NULL AND home_bullpen_avg_li < 0.0) AS invalid_h_bp_li,
    count(*) FILTER (WHERE away_bullpen_avg_li IS NOT NULL AND away_bullpen_avg_li < 0.0) AS invalid_a_bp_li
FROM gold.game_feature;
