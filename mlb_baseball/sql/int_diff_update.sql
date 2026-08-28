-- Home-minus-away interaction terms (INT-01, INT-02, docs/FEATURE_ADMISSION_QUEUE.md,
-- ADR-081, ADR-099). Pure algebra derived from already-populated gold.game_feature
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
    wrc_plus_diff = home_wrc_plus - away_wrc_plus,
    starter_siera_diff = home_starter_siera - away_starter_siera,
    starter_xfip_diff = home_starter_xfip - away_starter_xfip,
    starter_csw_diff = home_starter_csw_pct - away_starter_csw_pct,
    starter_whiff_diff = home_starter_whiff_pct - away_starter_whiff_pct,
    starter_xwoba_diff = home_starter_xwoba - away_starter_xwoba,
    starter_fastball_velo_diff = home_starter_fastball_velo - away_starter_fastball_velo,
    starter_vert_sep_diff = home_starter_vert_separation_in - away_starter_vert_separation_in,
    bullpen_siera_diff = home_bullpen_siera - away_bullpen_siera,
    bullpen_xfip_diff = home_bullpen_xfip - away_bullpen_xfip,
    bullpen_csw_diff = home_bullpen_csw_pct - away_bullpen_csw_pct,
    bullpen_whiff_diff = home_bullpen_whiff_pct - away_bullpen_whiff_pct,
    bullpen_xwoba_diff = home_bullpen_xwoba - away_bullpen_xwoba,
    offense_hard_hit_diff = home_offense_hard_hit_pct - away_offense_hard_hit_pct,
    offense_barrel_diff = home_offense_barrel_pct - away_offense_barrel_pct,
    offense_xwoba_diff = home_offense_xwoba - away_offense_xwoba,
    bsr_total_diff = home_bsr_total - away_bsr_total,
    catcher_framing_diff = home_catcher_csae_pct - away_catcher_csae_pct
WHERE TRUE;
