-- Snapshot rows are evidence for a completed experiment.  They are never
-- revised in place: a corrected feature build creates a new content-addressed
-- snapshot.  Rules work here without procedural migration code, and TRUNCATE
-- remains available for isolated mlb_test fixture cleanup.

CREATE RULE game_feature_snapshot_no_update AS
    ON UPDATE TO gold.game_feature_snapshot DO INSTEAD NOTHING;

CREATE RULE game_feature_snapshot_no_delete AS
    ON DELETE TO gold.game_feature_snapshot DO INSTEAD NOTHING;

CREATE RULE experiment_snapshot_no_update AS
    ON UPDATE TO meta.experiment_snapshot DO INSTEAD NOTHING;

CREATE RULE experiment_snapshot_no_delete AS
    ON DELETE TO meta.experiment_snapshot DO INSTEAD NOTHING;
