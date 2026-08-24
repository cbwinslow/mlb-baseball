-- Live Game State & Player Props Serving Views (PROP-01, LIVE-01, ADR-107).
-- Extends the `serve` schema with proposition market analysis and live game tracking.

-- 1. Starting Pitcher Props & Matchup Projections Mart
CREATE OR REPLACE VIEW serve.pitcher_prop_market AS
SELECT
    f.game_instance_key,
    f.mlb_game_pk,
    f.game_date,
    -- Home starter
    f.home_starter_id,
    NULLIF(CONCAT_WS(' ', hsp.first_name, hsp.last_name), '') AS home_starter_name,
    f.home_starter_k_pct,
    f.home_starter_rest_days,
    f.away_k_pct AS away_opponent_k_pct,
    ROUND(
        ((f.home_starter_k_pct / NULLIF(1.0 - f.home_starter_k_pct, 0.0)) *
         (f.away_k_pct / NULLIF(1.0 - f.away_k_pct, 0.0)) /
         (0.225 / 0.775)) /
        NULLIF(1.0 + ((f.home_starter_k_pct / NULLIF(1.0 - f.home_starter_k_pct, 0.0)) *
                (f.away_k_pct / NULLIF(1.0 - f.away_k_pct, 0.0)) /
                (0.225 / 0.775)), 0.0),
        4
    ) AS home_starter_projected_k_pct,
    -- Away starter
    f.away_starter_id,
    NULLIF(CONCAT_WS(' ', asp.first_name, asp.last_name), '') AS away_starter_name,
    f.away_starter_k_pct,
    f.away_starter_rest_days,
    f.home_k_pct AS home_opponent_k_pct,
    ROUND(
        ((f.away_starter_k_pct / NULLIF(1.0 - f.away_starter_k_pct, 0.0)) *
         (f.home_k_pct / NULLIF(1.0 - f.home_k_pct, 0.0)) /
         (0.225 / 0.775)) /
        NULLIF(1.0 + ((f.away_starter_k_pct / NULLIF(1.0 - f.away_starter_k_pct, 0.0)) *
                (f.home_k_pct / NULLIF(1.0 - f.home_k_pct, 0.0)) /
                (0.225 / 0.775)), 0.0),
        4
    ) AS away_starter_projected_k_pct
FROM gold.game_feature f
LEFT JOIN core.player hsp ON hsp.id = f.home_starter_id
LEFT JOIN core.player asp ON asp.id = f.away_starter_id
WHERE f.home_starter_id IS NOT NULL OR f.away_starter_id IS NOT NULL;

-- 2. Live In-Play Game Tracking Mart
CREATE OR REPLACE VIEW serve.live_game_tracker AS
SELECT
    f.game_instance_key,
    f.mlb_game_pk,
    f.game_date,
    f.season,
    ht.retro_team_id AS home_team,
    at.retro_team_id AS away_team,
    f.home_starter_siera,
    f.away_starter_siera,
    f.home_platoon_matchup_woba_diff,
    f.away_platoon_matchup_woba_diff,
    g.home_score AS current_home_score,
    g.away_score AS current_away_score,
    f.home_win AS actual_home_win
FROM gold.game_feature f
LEFT JOIN core.game g ON g.id = f.game_id
LEFT JOIN core.team ht ON ht.id = f.home_team_id
LEFT JOIN core.team at ON at.id = f.away_team_id;

-- 3. Upgrade Daily Betting Grid to support both gbm-v1 and gbm-v2
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
    COALESCE(p_gbm2.home_win_prob, p_gbm1.home_win_prob) AS gbm_home_win_prob,
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
LEFT JOIN gold.prediction p_gbm1 ON p_gbm1.game_instance_key = f.game_instance_key AND p_gbm1.model_version = 'gbm-v1'
LEFT JOIN gold.prediction p_gbm2 ON p_gbm2.game_instance_key = f.game_instance_key AND p_gbm2.model_version = 'gbm-v2';
