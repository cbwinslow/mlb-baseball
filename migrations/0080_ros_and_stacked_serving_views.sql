-- Rest-of-Season Standings, Matchup Dossiers & Consensus Serving Views (SERVE-02, ADR-123).
-- Establishes high-performance analytical marts for the Astro web frontend and API.

-- 1. In-Season Team Standings & Pythagorean True Talent Mart
CREATE OR REPLACE VIEW serve.ros_team_standings AS
WITH completed AS (
    SELECT
        EXTRACT(YEAR FROM g.game_date)::INTEGER AS season,
        g.home_team_id,
        g.away_team_id,
        g.home_score,
        g.away_score,
        CASE WHEN g.home_score > g.away_score THEN 1 ELSE 0 END AS home_win,
        CASE WHEN g.away_score > g.home_score THEN 1 ELSE 0 END AS away_win
    FROM core.game g
    WHERE g.home_score IS NOT NULL AND g.away_score IS NOT NULL
),
team_records AS (
    -- Home games
    SELECT
        season,
        home_team_id AS team_id,
        home_win AS win,
        away_win AS loss,
        home_score AS runs_for,
        away_score AS runs_against
    FROM completed
    UNION ALL
    -- Away games
    SELECT
        season,
        away_team_id AS team_id,
        away_win AS win,
        home_win AS loss,
        away_score AS runs_for,
        home_score AS runs_against
    FROM completed
)
SELECT
    tr.season,
    t.id AS team_id,
    t.retro_team_id AS team_code,
    t.name AS team_name,
    t.league,
    t.division,
    COUNT(*)::INTEGER AS games_played,
    SUM(tr.win)::INTEGER AS wins,
    SUM(tr.loss)::INTEGER AS losses,
    ROUND(SUM(tr.win)::NUMERIC / NULLIF(COUNT(*), 0), 3) AS win_pct,
    SUM(tr.runs_for)::INTEGER AS runs_for,
    SUM(tr.runs_against)::INTEGER AS runs_against,
    (SUM(tr.runs_for) - SUM(tr.runs_against))::INTEGER AS run_differential,
    ROUND(
        POWER(SUM(tr.runs_for)::NUMERIC, 1.83) /
        NULLIF(POWER(SUM(tr.runs_for)::NUMERIC, 1.83) + POWER(SUM(tr.runs_against)::NUMERIC, 1.83), 0),
        3
    ) AS pythagorean_win_pct
FROM team_records tr
JOIN core.team t ON t.id = tr.team_id
GROUP BY tr.season, t.id, t.retro_team_id, t.name, t.league, t.division;

-- 2. Comprehensive Matchup Dossier Serving Mart
CREATE OR REPLACE VIEW serve.matchup_dossier AS
WITH latest_preds AS (
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
    f.season,
    -- Teams
    ht.retro_team_id AS home_team,
    at.retro_team_id AS away_team,
    -- Starting Pitchers
    f.home_starter_id,
    NULLIF(CONCAT_WS(' ', hsp.first_name, hsp.last_name), '') AS home_starter_name,
    f.away_starter_id,
    NULLIF(CONCAT_WS(' ', asp.first_name, asp.last_name), '') AS away_starter_name,
    -- Starter Quality Metrics
    f.home_starter_siera,
    f.away_starter_siera,
    f.home_starter_xfip,
    f.away_starter_xfip,
    f.home_starter_csw_pct,
    f.away_starter_csw_pct,
    f.home_starter_fastball_velo,
    f.away_starter_fastball_velo,
    -- Pitch Movement
    f.home_starter_fastball_ivb_in,
    f.away_starter_fastball_ivb_in,
    f.home_starter_curve_drop_in,
    f.away_starter_curve_drop_in,
    -- Bullpen & Offense Quality
    f.home_bullpen_siera,
    f.away_bullpen_siera,
    f.home_wrc_plus,
    f.away_wrc_plus,
    -- Environmental Physics
    f.park_factor_3yr AS park_factor,
    f.air_density_index,
    f.effective_wind_speed,
    -- Model Predictions
    p_gbm.home_win_prob AS gbm_home_win_prob,
    p_log5.home_win_prob AS log5_home_win_prob,
    p_elo.home_win_prob AS elo_home_win_prob
FROM gold.game_feature f
JOIN core.team ht ON ht.id = f.home_team_id
JOIN core.team at ON at.id = f.away_team_id
LEFT JOIN core.player hsp ON hsp.id = f.home_starter_id
LEFT JOIN core.player asp ON asp.id = f.away_starter_id
LEFT JOIN latest_preds p_gbm ON p_gbm.mlb_game_pk = f.mlb_game_pk AND p_gbm.model_version IN ('gbm-v2', 'gbm-v1')
LEFT JOIN latest_preds p_log5 ON p_log5.mlb_game_pk = f.mlb_game_pk AND p_log5.model_version IN ('log5-v2', 'log5-v1')
LEFT JOIN latest_preds p_elo ON p_elo.mlb_game_pk = f.mlb_game_pk AND p_elo.model_version = 'elo-v1';

-- Comment on views
COMMENT ON VIEW serve.ros_team_standings IS 'Point-in-time in-season team standings, run differentials, and Pythagorean win expectations (SERVE-02).';
COMMENT ON VIEW serve.matchup_dossier IS 'High-density pre-joined quantitative matchup dossiers for the web research interface (SERVE-02).';
