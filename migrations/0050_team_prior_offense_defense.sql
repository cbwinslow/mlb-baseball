-- Team prior offense/defense (ADR-061, Plan 03G admission queue OFF-01/
-- OFF-02/OFF-03/OFF-08/DEF-01, docs/FEATURE_ADMISSION_QUEUE.md). Prior
-- rolling within-season OBP/SLG/ISO/BB%/K% from raw.retrosheet_event
-- (see mlb_baseball/model/team_rate.py::compute, same shape as
-- 0018_team_woba.sql) plus prior runs-for/allowed averages derived
-- directly from already-computed home_runs_for/home_wins/home_losses
-- (see team_rate.py::compute_run_environment) -- no new raw dependency
-- for the run-environment half.

ALTER TABLE gold.game_feature ADD COLUMN home_obp numeric;
ALTER TABLE gold.game_feature ADD COLUMN away_obp numeric;
ALTER TABLE gold.game_feature ADD COLUMN home_slg numeric;
ALTER TABLE gold.game_feature ADD COLUMN away_slg numeric;
ALTER TABLE gold.game_feature ADD COLUMN home_iso numeric;
ALTER TABLE gold.game_feature ADD COLUMN away_iso numeric;
ALTER TABLE gold.game_feature ADD COLUMN home_bb_pct numeric;
ALTER TABLE gold.game_feature ADD COLUMN away_bb_pct numeric;
ALTER TABLE gold.game_feature ADD COLUMN home_k_pct numeric;
ALTER TABLE gold.game_feature ADD COLUMN away_k_pct numeric;
ALTER TABLE gold.game_feature ADD COLUMN home_runs_for_avg numeric;
ALTER TABLE gold.game_feature ADD COLUMN away_runs_for_avg numeric;
ALTER TABLE gold.game_feature ADD COLUMN home_runs_allowed_avg numeric;
ALTER TABLE gold.game_feature ADD COLUMN away_runs_allowed_avg numeric;
