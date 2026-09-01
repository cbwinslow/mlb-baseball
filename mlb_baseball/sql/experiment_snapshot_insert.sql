-- One immutable, content-addressed snapshot row per approved PIT feature row.
-- Bulk-loaded via psycopg executemany from experiment.create_snapshot; the
-- snapshot_id is the same for every row in one call (see meta.experiment_snapshot).
INSERT INTO gold.game_feature_snapshot (
    snapshot_id, game_instance_key, mlb_game_pk, feature_cutoff_at,
    season, game_date, game_number, home_team_id, away_team_id,
    home_score, away_score, feature_json, home_win
) VALUES (
    %(snapshot_id)s, %(game_instance_key)s, %(mlb_game_pk)s, %(feature_cutoff_at)s,
    %(season)s, %(game_date)s, %(game_number)s, %(home_team_id)s, %(away_team_id)s,
    %(home_score)s, %(away_score)s, %(feature_json)s, %(home_win)s
)
