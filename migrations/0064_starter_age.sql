-- Starter age on game date (ADR-087, admission queue PLN-04,
-- docs/FEATURE_ADMISSION_QUEUE.md). Pure derived column over already-
-- resolved starter identity and core.player.birth_date -- no new raw
-- dependency.
--
-- Renumbered from 0059 to 0064 (ADR from 081 to 087) during rebase onto
-- main: BSR-01 (0059/ADR-081), INT-01 (0060/ADR-082), INT-02
-- (0061/ADR-083), and experience_v1 (0063/ADR-085, PLN-04's career-PA/IP
-- half) are all real and merged as of this rebase. This file was first
-- renumbered to 0062, which is numerically free -- but CI caught a real
-- bug: migrations run in filename order, so 0062 would run BEFORE
-- 0063_starter_experience.sql on a fresh database, referencing
-- home_starter_career_bf/away_starter_career_bf/home_starter_career_ip/
-- away_starter_career_ip before that migration creates them
-- (UndefinedColumn), and 0063's own already-merged CREATE OR REPLACE VIEW
-- would then silently drop this migration's age columns from the view
-- when it ran second. Renumbered again to 0064 -- the first number that
-- actually sorts after 0063 -- so this always runs strictly after
-- experience_v1 and its view extension is safe. The view below extends
-- 0063_starter_experience.sql's real current tail
-- (...home_starter_career_bf, away_starter_career_bf,
-- home_starter_career_ip, away_starter_career_ip) directly.

ALTER TABLE gold.game_feature ADD COLUMN home_starter_age numeric;
ALTER TABLE gold.game_feature ADD COLUMN away_starter_age numeric;

-- Extend the research export view (0058_game_export_view.sql) with the
-- new columns, appended at the end -- CREATE OR REPLACE VIEW refuses to
-- rename or reposition an existing view column.
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
    f.away_starter_age
FROM gold.game_feature f
LEFT JOIN core.game g ON g.id = f.game_id
LEFT JOIN core.team ht ON ht.id = f.home_team_id
LEFT JOIN core.team at ON at.id = f.away_team_id
LEFT JOIN core.venue v ON v.id = f.venue_id
LEFT JOIN core.player hsp ON hsp.id = f.home_starter_id
LEFT JOIN core.player asp ON asp.id = f.away_starter_id;
