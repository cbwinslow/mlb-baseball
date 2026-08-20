-- Home-minus-away interaction terms (INT-01, docs/FEATURE_ADMISSION_QUEUE.md,
-- ADR-081). Pure algebra derived from already-populated gold.game_feature
-- columns -- no new raw dependency, no join, same shape as
-- team_run_environment_update.sql. NULL if either side is unavailable
-- (subtracting a NULL always yields NULL in SQL, so no explicit CASE guard
-- is needed here).

UPDATE gold.game_feature
SET win_pct_diff = home_win_pct - away_win_pct,
    win_pct_10_diff = home_win_pct_10 - away_win_pct_10,
    pyth_wpct_diff = home_pyth_wpct - away_pyth_wpct,
    elo_diff = home_elo - away_elo,
    woba_diff = home_woba - away_woba,
    wrc_plus_diff = home_wrc_plus - away_wrc_plus
WHERE TRUE;
