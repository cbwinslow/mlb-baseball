-- Prior runs-for/allowed averages, derived from already-populated
-- gold.game_feature columns (OFF-08/DEF-01) -- no new raw dependency.
-- home_wins + home_losses is exactly the count of prior completed
-- season games, since features.build() only ever sets both from the
-- same season-to-date window (see game_feature_rebuild.sql).

UPDATE gold.game_feature
SET home_runs_for_avg = CASE WHEN (home_wins + home_losses) > 0
        THEN home_runs_for::numeric / (home_wins + home_losses) END,
    home_runs_allowed_avg = CASE WHEN (home_wins + home_losses) > 0
        THEN home_runs_allowed::numeric / (home_wins + home_losses) END,
    away_runs_for_avg = CASE WHEN (away_wins + away_losses) > 0
        THEN away_runs_for::numeric / (away_wins + away_losses) END,
    away_runs_allowed_avg = CASE WHEN (away_wins + away_losses) > 0
        THEN away_runs_allowed::numeric / (away_wins + away_losses) END
WHERE TRUE;
