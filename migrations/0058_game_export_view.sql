-- Owner-directed research-interoperability goal (docs/ROADMAP.md Phase 3
-- addendum, 2026-08-19): a wide, pre-joined, CSV/Excel/R-ready view over
-- everything gold.game_feature already carries, with human-readable team
-- names/starter names instead of internal bigint IDs, and the real final
-- score (gold.game_feature itself has no score columns, only home_win --
-- the score lives on core.game). A view, not a materialized table: every
-- column here is already computed and stored on gold.game_feature/
-- core.game; this only relabels and joins, so it needs no separate
-- refresh step and is always as fresh as gold.game_feature itself.
--
-- LEFT JOINs throughout: an upcoming (not yet played) game has no
-- core.game row yet, no venue/starter resolved, no score -- those columns
-- come back NULL for such a row rather than dropping it from the export.
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
    f.feature_cutoff_at
FROM gold.game_feature f
LEFT JOIN core.game g ON g.id = f.game_id
LEFT JOIN core.team ht ON ht.id = f.home_team_id
LEFT JOIN core.team at ON at.id = f.away_team_id
LEFT JOIN core.venue v ON v.id = f.venue_id
LEFT JOIN core.player hsp ON hsp.id = f.home_starter_id
LEFT JOIN core.player asp ON asp.id = f.away_starter_id;
