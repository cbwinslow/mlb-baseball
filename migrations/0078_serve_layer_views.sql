-- Serving Layer Views (SRV-01, ADR-102).
-- Establishes the clean, read-only `serve` schema for the research website and API.

CREATE SCHEMA IF NOT EXISTS serve;

-- 1. Daily Betting & Prediction Grid
CREATE OR REPLACE VIEW serve.daily_betting_grid AS
SELECT
    f.game_instance_key,
    f.mlb_game_pk,
    f.season,
    f.game_date,
    f.game_number,
    f.day_night,
    ht.retro_team_id AS home_team_code,
    NULLIF(CONCAT_WS(' ', ht.city, ht.nickname), '') AS home_team_name,
    at.retro_team_id AS away_team_code,
    NULLIF(CONCAT_WS(' ', at.city, at.nickname), '') AS away_team_name,
    v.name AS venue_name,
    f.temp_f,
    f.wind_speed_mph,
    f.wind_dir,
    NULLIF(CONCAT_WS(' ', hsp.first_name, hsp.last_name), '') AS home_starter_name,
    f.home_starter_throws,
    f.home_starter_siera,
    f.home_starter_csw_pct,
    NULLIF(CONCAT_WS(' ', asp.first_name, asp.last_name), '') AS away_starter_name,
    f.away_starter_throws,
    f.away_starter_siera,
    f.away_starter_csw_pct,
    -- Model probabilities
    f.home_pyth_wpct,
    f.away_pyth_wpct,
    f.home_elo,
    f.away_elo,
    p_log5.home_win_prob AS log5_home_win_prob,
    p_elo.home_win_prob AS elo_home_win_prob,
    p_gbm.home_win_prob AS gbm_home_win_prob,
    -- Difference vectors
    f.starter_siera_diff,
    f.bullpen_siera_diff,
    f.offense_xwoba_diff,
    f.home_platoon_matchup_woba_diff,
    f.away_platoon_matchup_woba_diff,
    -- Final outcomes if completed
    g.home_score,
    g.away_score,
    f.home_win
FROM gold.game_feature f
LEFT JOIN core.game g ON g.id = f.game_id
LEFT JOIN core.team ht ON ht.id = f.home_team_id
LEFT JOIN core.team at ON at.id = f.away_team_id
LEFT JOIN core.venue v ON v.id = f.venue_id
LEFT JOIN core.player hsp ON hsp.id = f.home_starter_id
LEFT JOIN core.player asp ON asp.id = f.away_starter_id
LEFT JOIN gold.prediction p_log5 ON p_log5.game_instance_key = f.game_instance_key AND p_log5.model_version = 'log5-v1'
LEFT JOIN gold.prediction p_elo ON p_elo.game_instance_key = f.game_instance_key AND p_elo.model_version = 'elo-v1'
LEFT JOIN gold.prediction p_gbm ON p_gbm.game_instance_key = f.game_instance_key AND p_gbm.model_version = 'gbm-v1';

-- 2. Pitcher Analytical Profile Card
CREATE OR REPLACE VIEW serve.pitcher_card AS
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

-- 3. Matchup Preview
CREATE OR REPLACE VIEW serve.matchup_preview AS
SELECT
    f.game_instance_key,
    f.game_date,
    ht.retro_team_id AS home_team,
    at.retro_team_id AS away_team,
    v.name AS venue,
    f.park_factor_3yr AS park_factor,
    f.air_density_index,
    f.effective_wind_speed,
    f.home_starter_siera,
    f.away_starter_siera,
    f.home_starter_vert_separation_in,
    f.away_starter_vert_separation_in,
    f.home_bullpen_siera,
    f.away_bullpen_siera,
    f.home_offense_xwoba,
    f.away_offense_xwoba,
    f.home_catcher_csae_pct,
    f.away_catcher_csae_pct,
    f.starter_siera_diff,
    f.starter_vert_sep_diff,
    f.bullpen_siera_diff,
    f.offense_xwoba_diff,
    f.bsr_total_diff,
    f.catcher_framing_diff,
    f.home_platoon_matchup_woba_diff,
    f.away_platoon_matchup_woba_diff
FROM gold.game_feature f
LEFT JOIN core.team ht ON ht.id = f.home_team_id
LEFT JOIN core.team at ON at.id = f.away_team_id
LEFT JOIN core.venue v ON v.id = f.venue_id;

-- 4. Prediction Market +EV Alpha Screener
CREATE OR REPLACE VIEW serve.prediction_market_alpha AS
SELECT
    f.game_instance_key,
    f.game_date,
    ht.retro_team_id AS home_team,
    at.retro_team_id AS away_team,
    m.source AS market_source,
    m.implied_probability AS market_home_prob,
    COALESCE(p_gbm.home_win_prob, p_elo.home_win_prob, p_log5.home_win_prob) AS model_home_win_prob,
    ROUND(
        COALESCE(p_gbm.home_win_prob, p_elo.home_win_prob, p_log5.home_win_prob) - m.implied_probability,
        4
    ) AS home_edge_alpha,
    CASE
        WHEN (COALESCE(p_gbm.home_win_prob, p_elo.home_win_prob, p_log5.home_win_prob) - m.implied_probability) >= 0.025 THEN 'BUY_HOME_YES'
        WHEN (m.implied_probability - COALESCE(p_gbm.home_win_prob, p_elo.home_win_prob, p_log5.home_win_prob)) >= 0.025 THEN 'BUY_AWAY_YES'
        ELSE 'PASS'
    END AS recommendation
FROM gold.game_feature f
JOIN core.market m ON m.game_id = f.game_id AND m.team_id = f.home_team_id
LEFT JOIN core.team ht ON ht.id = f.home_team_id
LEFT JOIN core.team at ON at.id = f.away_team_id
LEFT JOIN gold.prediction p_gbm ON p_gbm.game_instance_key = f.game_instance_key AND p_gbm.model_version = 'gbm-v1'
LEFT JOIN gold.prediction p_elo ON p_elo.game_instance_key = f.game_instance_key AND p_elo.model_version = 'elo-v1'
LEFT JOIN gold.prediction p_log5 ON p_log5.game_instance_key = f.game_instance_key AND p_log5.model_version = 'log5-v1';
