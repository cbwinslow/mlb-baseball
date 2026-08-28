-- Correct serving views installed by 0081 without rewriting applied history.
--
-- gold.prediction retains every model generation for provenance. Serving
-- contracts must select the latest generation per game/model, otherwise a
-- game is repeated once for each historical prediction run.

CREATE OR REPLACE VIEW serve.sgp_matchup_grid AS
WITH latest_predictions AS (
    SELECT DISTINCT ON (mlb_game_pk, model_version)
        mlb_game_pk,
        model_version,
        home_win_prob
    FROM gold.prediction
    ORDER BY mlb_game_pk, model_version, generated_at DESC
)
SELECT
    f.game_instance_key,
    f.mlb_game_pk,
    f.game_date,
    f.home_team_id,
    ht.retro_team_id AS home_team_code,
    f.away_team_id,
    at.retro_team_id AS away_team_code,
    f.venue_id,
    COALESCE(p_gbm.home_win_prob, p_log5.home_win_prob, 0.54) AS home_win_prob,
    f.home_starter_k_pct,
    f.away_starter_k_pct,
    f.home_runs_for_avg AS home_expected_runs,
    f.away_runs_for_avg AS away_expected_runs,
    ROUND((COALESCE(f.home_runs_for_avg, 4.5) + COALESCE(f.away_runs_for_avg, 4.2))::numeric, 1) AS game_total_runs,
    f.park_factor,
    f.air_density_index,
    f.effective_wind_speed
FROM gold.game_feature f
JOIN core.team ht ON ht.id = f.home_team_id
JOIN core.team at ON at.id = f.away_team_id
LEFT JOIN latest_predictions p_gbm
    ON p_gbm.mlb_game_pk = f.mlb_game_pk
   AND p_gbm.model_version = 'gbm-v2'
LEFT JOIN latest_predictions p_log5
    ON p_log5.mlb_game_pk = f.mlb_game_pk
   AND p_log5.model_version = 'log5-v2';

CREATE OR REPLACE VIEW serve.pitcher_arsenal AS
SELECT
    f.home_starter_id AS pitcher_id,
    NULLIF(CONCAT_WS(' ', p.first_name, p.last_name), '') AS pitcher_name,
    f.season,
    f.home_starter_throws AS throws,
    f.home_starter_fastball_velo AS fastball_velo_mph,
    f.home_starter_fastball_ivb_in AS fastball_ivb_in,
    f.home_starter_curve_drop_in AS curve_drop_in,
    f.home_starter_vert_separation_in AS vert_separation_in,
    f.home_starter_spin_rate_rpm AS spin_rate_rpm,
    f.home_starter_csw_pct AS csw_pct,
    f.home_starter_whiff_pct AS whiff_pct,
    f.home_starter_siera AS siera,
    f.home_starter_xfip AS xfip,
    ROUND(
        (100.0 + ((COALESCE(f.home_starter_fastball_velo, 94.0) - 94.0) / 2.2 * 7.5)
               + ((COALESCE(f.home_starter_fastball_ivb_in, 16.0) - 16.0) / 2.8 * 6.5))::numeric,
        1
    ) AS estimated_stuff_plus,
    ROUND(
        (100.0 + ((COALESCE(f.home_starter_csw_pct, 0.28) - 0.28) / 0.04 * 6.0))::numeric,
        1
    ) AS estimated_location_plus
FROM gold.game_feature f
LEFT JOIN core.player p ON p.id = f.home_starter_id
WHERE f.home_starter_id IS NOT NULL
  AND f.home_starter_fastball_velo IS NOT NULL
ORDER BY f.season DESC, f.game_date DESC;
