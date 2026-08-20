-- Recent-minus-long win-rate trend (INT-02, docs/FEATURE_ADMISSION_QUEUE.md,
-- ADR-081). Pure algebra derived from two already-populated
-- gold.game_feature columns per side -- no new raw dependency, no join,
-- same shape as int_diff_update.sql/team_run_environment_update.sql.
--
-- home_win_pct_10/away_win_pct_10 (trailing 10-game rolling rate) and
-- home_win_pct/away_win_pct (season-to-date expanding rate) are both
-- already computed by game_feature_rebuild.sql's own w_last10/w_season
-- windows (migration 0012) -- this is the one already-approved family
-- with both a "recent" and a "long" version already built, so unlike a
-- fresh rolling-window family, this needed zero new data or window SQL.
-- Positive means the team is playing better lately than its season rate;
-- negative means worse. NULL if either side is unavailable (subtracting
-- a NULL is NULL in SQL).

UPDATE gold.game_feature
SET home_win_pct_trend = home_win_pct_10 - home_win_pct,
    away_win_pct_trend = away_win_pct_10 - away_win_pct
WHERE TRUE;
