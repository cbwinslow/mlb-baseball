-- Batted-ball profile metrics (ADR-090, admission queue BAT-01 / OFF-10,
-- docs/FEATURE_ADMISSION_QUEUE.md). Point-in-time entering GB%, FB%, LD%, and
-- HR/FB% for starting pitchers, bullpens, and offensive lineups.

-- Starter batted-ball rates
ALTER TABLE gold.game_feature ADD COLUMN home_starter_gb_pct numeric;
ALTER TABLE gold.game_feature ADD COLUMN away_starter_gb_pct numeric;
ALTER TABLE gold.game_feature ADD COLUMN home_starter_fb_pct numeric;
ALTER TABLE gold.game_feature ADD COLUMN away_starter_fb_pct numeric;
ALTER TABLE gold.game_feature ADD COLUMN home_starter_ld_pct numeric;
ALTER TABLE gold.game_feature ADD COLUMN away_starter_ld_pct numeric;
ALTER TABLE gold.game_feature ADD COLUMN home_starter_hr_per_fb numeric;
ALTER TABLE gold.game_feature ADD COLUMN away_starter_hr_per_fb numeric;

-- Bullpen batted-ball rates
ALTER TABLE gold.game_feature ADD COLUMN home_bullpen_gb_pct numeric;
ALTER TABLE gold.game_feature ADD COLUMN away_bullpen_gb_pct numeric;
ALTER TABLE gold.game_feature ADD COLUMN home_bullpen_fb_pct numeric;
ALTER TABLE gold.game_feature ADD COLUMN away_bullpen_fb_pct numeric;
ALTER TABLE gold.game_feature ADD COLUMN home_bullpen_hr_per_fb numeric;
ALTER TABLE gold.game_feature ADD COLUMN away_bullpen_hr_per_fb numeric;

-- Team batting batted-ball rates
ALTER TABLE gold.game_feature ADD COLUMN home_batting_gb_pct numeric;
ALTER TABLE gold.game_feature ADD COLUMN away_batting_gb_pct numeric;
ALTER TABLE gold.game_feature ADD COLUMN home_batting_fb_pct numeric;
ALTER TABLE gold.game_feature ADD COLUMN away_batting_fb_pct numeric;
ALTER TABLE gold.game_feature ADD COLUMN home_batting_ld_pct numeric;
ALTER TABLE gold.game_feature ADD COLUMN away_batting_ld_pct numeric;
ALTER TABLE gold.game_feature ADD COLUMN home_batting_hr_per_fb numeric;
ALTER TABLE gold.game_feature ADD COLUMN away_batting_hr_per_fb numeric;

-- Extend the research export view (0058_game_export_view.sql / 0066_pitch_discipline.sql)
-- with the new columns, appended at the end of the SELECT list.
CREATE OR REPLACE VIEW gold.game_export AS
SELECT
    f.game_instance_key,
    f.mlb_game_pk,
    f.season,
    f.game_date,
    f.game_number,
    NULLIF(CONCAT_WS(' ', ht.city, ht.nickname), '') AS home_team,
    NULLIF(CONCAT_WS(' ', at.city, at.nickname), '') AS away_team,
    ht.retro_team_id AS home_team_code,
    at.retro_team_id AS away_team_code,
    g.home_score,
    g.away_score,
    f.home_win,
    f.home_field,
    v.name AS venue_name,
    f.day_night,
    f.temp_f,
    f.wind_dir,
    f.wind_speed_mph,
    f.sky,
    f.precip,
    f.home_win_pct,
    f.away_win_pct,
    f.home_win_pct_10,
    f.away_win_pct_10,
    f.home_wins,
    f.home_losses,
    f.away_wins,
    f.away_losses,
    f.home_run_diff,
    f.away_run_diff,
    f.home_pyth_wpct,
    f.away_pyth_wpct,
    f.home_elo,
    f.away_elo,
    f.home_rest,
    f.away_rest,
    NULLIF(CONCAT_WS(' ', hsp.first_name, hsp.last_name), '') AS home_starter,
    NULLIF(CONCAT_WS(' ', asp.first_name, asp.last_name), '') AS away_starter,
    f.home_starter_era,
    f.away_starter_era,
    f.home_starter_rest,
    f.away_starter_rest,
    f.home_starter_k_pct,
    f.away_starter_k_pct,
    f.home_starter_bb_pct,
    f.away_starter_bb_pct,
    f.home_starter_hr_pct,
    f.away_starter_hr_pct,
    f.home_starter_rest_days,
    f.away_starter_rest_days,
    f.home_starter_outs_7d,
    f.away_starter_outs_7d,
    f.home_pa,
    f.away_pa,
    f.home_obp,
    f.away_obp,
    f.home_slg,
    f.away_slg,
    f.home_iso,
    f.away_iso,
    f.home_bb_pct,
    f.away_bb_pct,
    f.home_k_pct,
    f.away_k_pct,
    f.home_babip,
    f.away_babip,
    f.home_woba,
    f.away_woba,
    f.home_wrc_plus,
    f.away_wrc_plus,
    f.home_runs_for,
    f.away_runs_for,
    f.home_runs_allowed,
    f.away_runs_allowed,
    f.home_runs_for_avg,
    f.away_runs_for_avg,
    f.home_runs_allowed_avg,
    f.away_runs_allowed_avg,
    f.home_bullpen_fip,
    f.away_bullpen_fip,
    f.home_bullpen_k_pct,
    f.away_bullpen_k_pct,
    f.home_bullpen_bb_pct,
    f.away_bullpen_bb_pct,
    f.home_bullpen_fatigue,
    f.away_bullpen_fatigue,
    f.home_oaa_prior,
    f.away_oaa_prior,
    f.home_speed_prior,
    f.away_speed_prior,
    f.home_framing_prior,
    f.away_framing_prior,
    f.home_war_prior,
    f.away_war_prior,
    f.park_factor,
    f.feature_cutoff_at,
    f.home_sb,
    f.away_sb,
    f.home_cs,
    f.away_cs,
    f.home_wsb,
    f.away_wsb,
    f.win_pct_diff,
    f.win_pct_10_diff,
    f.pyth_wpct_diff,
    f.elo_diff,
    f.woba_diff,
    f.wrc_plus_diff,
    f.home_win_pct_trend,
    f.away_win_pct_trend,
    f.home_starter_career_bf,
    f.away_starter_career_bf,
    f.home_starter_career_ip,
    f.away_starter_career_ip,
    f.home_starter_age,
    f.away_starter_age,
    f.home_starter_csw_pct,
    f.away_starter_csw_pct,
    f.home_starter_whiff_pct,
    f.away_starter_whiff_pct,
    f.home_starter_fstrike_pct,
    f.away_starter_fstrike_pct,
    f.home_bullpen_csw_pct,
    f.away_bullpen_csw_pct,
    f.home_bullpen_whiff_pct,
    f.away_bullpen_whiff_pct,
    f.home_starter_gb_pct,
    f.away_starter_gb_pct,
    f.home_starter_fb_pct,
    f.away_starter_fb_pct,
    f.home_starter_ld_pct,
    f.away_starter_ld_pct,
    f.home_starter_hr_per_fb,
    f.away_starter_hr_per_fb,
    f.home_bullpen_gb_pct,
    f.away_bullpen_gb_pct,
    f.home_bullpen_fb_pct,
    f.away_bullpen_fb_pct,
    f.home_bullpen_hr_per_fb,
    f.away_bullpen_hr_per_fb,
    f.home_batting_gb_pct,
    f.away_batting_gb_pct,
    f.home_batting_fb_pct,
    f.away_batting_fb_pct,
    f.home_batting_ld_pct,
    f.away_batting_ld_pct,
    f.home_batting_hr_per_fb,
    f.away_batting_hr_per_fb
FROM gold.game_feature f
LEFT JOIN core.game g ON g.id = f.game_id
LEFT JOIN core.team ht ON ht.id = f.home_team_id
LEFT JOIN core.team at ON at.id = f.away_team_id
LEFT JOIN core.venue v ON v.id = f.venue_id
LEFT JOIN core.player hsp ON hsp.id = f.home_starter_id
LEFT JOIN core.player asp ON asp.id = f.away_starter_id;
