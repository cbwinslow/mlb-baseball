-- Correct remaining serving views left over from 0078/0079 that still join
-- gold.prediction directly, without rewriting applied history (same
-- forward-only pattern as 0082, which fixed serve.sgp_matchup_grid and
-- serve.pitcher_arsenal but missed these two).
--
-- gold.prediction intentionally retains every prediction snapshot ever
-- generated for a game/model (see mlb_baseball/model/evaluation.py's own
-- docstring) -- a still-upcoming game accumulates one new row per cron
-- cycle (`mlb predict`, daily) until it starts. Joining directly on
-- (game_instance_key, model_version) without selecting the latest
-- generated_at, as serve.daily_betting_grid and serve.prediction_market_alpha
-- both did, fans out: one gold.game_feature row becomes N rows, one per
-- historical snapshot, in the serving grid a person or the Astro site would
-- read. Found by re-verifying prediction-boundary consumers against the
-- canonical game identity contract (Plan 01F-R5, plans/01-correctness-
-- rights-security.md), the same review that already caught this pattern
-- once in 0082 -- it just didn't reach every view built on the same shape.
-- See docs/DECISIONS.md ADR-255.

CREATE OR REPLACE VIEW serve.daily_betting_grid AS
WITH latest_predictions AS (
    SELECT DISTINCT ON (game_instance_key, model_version)
        game_instance_key,
        model_version,
        home_win_prob
    FROM gold.prediction
    ORDER BY game_instance_key, model_version, generated_at DESC
)
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
LEFT JOIN latest_predictions p_log5
    ON p_log5.game_instance_key = f.game_instance_key AND p_log5.model_version = 'log5-v1'
LEFT JOIN latest_predictions p_elo
    ON p_elo.game_instance_key = f.game_instance_key AND p_elo.model_version = 'elo-v1'
LEFT JOIN latest_predictions p_gbm1
    ON p_gbm1.game_instance_key = f.game_instance_key AND p_gbm1.model_version = 'gbm-v1'
LEFT JOIN latest_predictions p_gbm2
    ON p_gbm2.game_instance_key = f.game_instance_key AND p_gbm2.model_version = 'gbm-v2';

CREATE OR REPLACE VIEW serve.prediction_market_alpha AS
WITH latest_predictions AS (
    SELECT DISTINCT ON (game_instance_key, model_version)
        game_instance_key,
        model_version,
        home_win_prob
    FROM gold.prediction
    ORDER BY game_instance_key, model_version, generated_at DESC
)
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
LEFT JOIN latest_predictions p_gbm
    ON p_gbm.game_instance_key = f.game_instance_key AND p_gbm.model_version = 'gbm-v1'
LEFT JOIN latest_predictions p_elo
    ON p_elo.game_instance_key = f.game_instance_key AND p_elo.model_version = 'elo-v1'
LEFT JOIN latest_predictions p_log5
    ON p_log5.game_instance_key = f.game_instance_key AND p_log5.model_version = 'log5-v1';
