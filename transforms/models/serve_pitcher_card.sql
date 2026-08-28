MODEL (
  name serve.pitcher_card,
  kind FULL,
  cron '@daily',
  grain (player_id, as_of_date)
);

SELECT
    p.id AS player_id,
    p.mlbam_id,
    p.retro_id,
    NULLIF(CONCAT_WS(' ', p.first_name, p.last_name), '') AS full_name,
    f.home_starter_throws AS throws,
    f.season,
    f.game_date AS as_of_date,
    f.home_starter_era AS era,
    f.home_starter_xfip AS xfip,
    f.home_starter_siera AS siera,
    f.home_starter_k_pct AS k_pct,
    f.home_starter_bb_pct AS bb_pct,
    f.home_starter_csw_pct AS csw_pct,
    f.home_starter_whiff_pct AS whiff_pct,
    f.home_starter_fastball_velo AS fastball_velo,
    f.home_starter_fastball_ivb_in AS fastball_ivb_in,
    f.home_starter_curve_drop_in AS curve_drop_in,
    f.home_starter_vert_separation_in AS vert_separation_in,
    f.home_starter_spin_rate_rpm AS spin_rate_rpm,
    f.home_starter_heart_pct AS heart_pct,
    f.home_starter_shadow_pct AS shadow_pct,
    f.home_starter_chase_pct AS chase_pct,
    f.home_starter_vs_lhb_woba AS vs_lhb_woba,
    f.home_starter_vs_rhb_woba AS vs_rhb_woba,
    f.home_starter_vs_lhb_k_pct AS vs_lhb_k_pct,
    f.home_starter_vs_rhb_k_pct AS vs_rhb_k_pct
FROM gold.game_feature f
JOIN core.player p ON p.id = f.home_starter_id
WHERE f.home_starter_id IS NOT NULL;
