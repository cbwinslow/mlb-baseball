-- Migration 0081: Deep Modeling Serving Views (SERVE-03, ADR-129)
-- Creates high-performance read-only analytical serving marts for:
-- 1. serve.pitcher_arsenal: Pitcher physical pitch movement, velocity, and arsenal ratings.
-- 2. serve.sgp_matchup_grid: Pre-joined correlated Same-Game Parlay (SGP) candidate legs.
-- 3. serve.batted_ball_profile: Player contact quality, exit velocity, and barrel metrics.

CREATE OR REPLACE VIEW serve.pitcher_arsenal AS
SELECT
    f.home_starter_id AS pitcher_id,
    p.name_common AS pitcher_name,
    f.season,
    'R' AS throws,
    f.home_starter_fastball_velo AS fastball_velo_mph,
    f.home_starter_fastball_ivb_in AS fastball_ivb_in,
    f.home_starter_curve_drop_in AS curve_drop_in,
    f.home_starter_vert_separation_in AS vert_separation_in,
    f.home_starter_spin_rate_rpm AS spin_rate_rpm,
    f.home_starter_csw_pct AS csw_pct,
    f.home_starter_whiff_pct AS whiff_pct,
    f.home_starter_siera AS siera,
    f.home_starter_xfip AS xfip,
    -- Benchmark Stuff+ estimation based on fastball velocity and IVB
    ROUND(
        (100.0 + ((COALESCE(f.home_starter_fastball_velo, 94.0) - 94.0) / 2.2 * 7.5)
               + ((COALESCE(f.home_starter_fastball_ivb_in, 16.0) - 16.0) / 2.8 * 6.5))::numeric,
        1
    ) AS estimated_stuff_plus,
    -- Benchmark Location+ estimation based on CSW% and command
    ROUND(
        (100.0 + ((COALESCE(f.home_starter_csw_pct, 0.28) - 0.28) / 0.04 * 6.0))::numeric,
        1
    ) AS estimated_location_plus
FROM gold.game_feature f
LEFT JOIN core.player p ON p.id = f.home_starter_id
WHERE f.home_starter_id IS NOT NULL
  AND f.home_starter_fastball_velo IS NOT NULL
ORDER BY f.season DESC, f.game_date DESC;

CREATE OR REPLACE VIEW serve.sgp_matchup_grid AS
SELECT
    g.game_instance_key,
    g.mlb_game_pk,
    g.game_date,
    g.home_team_id,
    ht.abbrev AS home_team_code,
    g.away_team_id,
    at.abbrev AS away_team_code,
    g.venue_id,
    -- Model probabilities
    COALESCE(p_gbm.home_win_prob, p_log5.home_win_prob, 0.54) AS home_win_prob,
    -- Pitcher Strikeout Expectations
    f.home_starter_k_pct AS home_starter_k_pct,
    f.away_starter_k_pct AS away_starter_k_pct,
    -- Projected Runs
    f.home_runs_for_avg AS home_expected_runs,
    f.away_runs_for_avg AS away_expected_runs,
    ROUND((COALESCE(f.home_runs_for_avg, 4.5) + COALESCE(f.away_runs_for_avg, 4.2))::numeric, 1) AS game_total_runs,
    -- Environmental Physics
    f.park_factor,
    f.air_density_index,
    f.effective_wind_speed
FROM core.game g
JOIN core.team ht ON ht.id = g.home_team_id
JOIN core.team at ON at.id = g.away_team_id
LEFT JOIN gold.game_feature f ON f.game_id = g.id
LEFT JOIN gold.prediction p_gbm ON p_gbm.mlb_game_pk = g.game_pk AND p_gbm.model_version = 'gbm-v2'
LEFT JOIN gold.prediction p_log5 ON p_log5.mlb_game_pk = g.game_pk AND p_log5.model_version = 'log5-v2'
WHERE g.status IN ('scheduled', 'pre-game', 'in_progress', 'final');

CREATE OR REPLACE VIEW serve.batted_ball_profile AS
SELECT
    f.game_instance_key,
    f.game_date,
    f.home_team_id,
    f.away_team_id,
    f.home_offense_hard_hit_pct AS home_hard_hit_pct,
    f.away_offense_hard_hit_pct AS away_hard_hit_pct,
    f.home_offense_barrel_pct AS home_barrel_pct,
    f.away_offense_barrel_pct AS away_barrel_pct,
    f.home_offense_xwoba AS home_xwoba,
    f.away_offense_xwoba AS away_xwoba,
    f.home_offense_xba AS home_xba,
    f.away_offense_xba AS away_xba,
    f.home_batting_gb_pct AS home_gb_pct,
    f.home_batting_fb_pct AS home_fb_pct,
    f.home_batting_ld_pct AS home_ld_pct
FROM gold.game_feature f
WHERE f.home_offense_hard_hit_pct IS NOT NULL;
