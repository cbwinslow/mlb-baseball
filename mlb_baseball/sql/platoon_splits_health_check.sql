-- Health check assertions for Platoon Splits & Handedness Matchups (PLT-01, ADR-101).
SELECT
    COUNT(*) AS total_rows,
    COUNT(*) FILTER (WHERE home_starter_throws NOT IN ('L', 'R') AND home_starter_throws IS NOT NULL) AS invalid_home_throws,
    COUNT(*) FILTER (WHERE away_starter_throws NOT IN ('L', 'R') AND away_starter_throws IS NOT NULL) AS invalid_away_throws,
    COUNT(*) FILTER (WHERE home_platoon_matchup_woba_diff < -0.300 OR home_platoon_matchup_woba_diff > 0.300) AS out_of_bounds_home_diff,
    COUNT(*) FILTER (WHERE away_platoon_matchup_woba_diff < -0.300 OR away_platoon_matchup_woba_diff > 0.300) AS out_of_bounds_away_diff
FROM gold.game_feature;
