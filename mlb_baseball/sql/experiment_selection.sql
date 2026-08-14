-- Experiment snapshot feature matrix selection query
SELECT f.game_instance_key, f.mlb_game_pk, f.feature_cutoff_at, f.season, f.game_date,
       f.game_number, f.home_team_id, f.away_team_id, f.home_win,
       g.home_score, g.away_score,
       f.home_wins, f.home_losses, f.away_wins, f.away_losses,
       f.home_runs_for, f.home_runs_allowed, f.away_runs_for, f.away_runs_allowed,
       f.home_rest, f.away_rest, f.home_field, f.home_win_pct, f.away_win_pct
FROM gold.game_feature f
JOIN core.game g ON g.id = f.game_id
WHERE f.home_win IS NOT NULL
  AND f.mlb_game_pk IS NOT NULL
  AND f.feature_cutoff_at IS NOT NULL
  AND g.home_score IS NOT NULL AND g.away_score IS NOT NULL
ORDER BY f.feature_cutoff_at, f.game_number NULLS LAST, f.mlb_game_pk, f.game_instance_key;
