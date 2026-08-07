-- mlb:nontransactional
-- game_pk is an MLB lookup identifier, not a unique game-instance key.  The
-- former primary key prevented two legitimate instances sharing a game_pk
-- from being predicted by the same model at the same instant.
--
-- 0034 first gives every retained row a non-null game_instance_key, so this
-- forward-only constraint replacement preserves every historical row.
ALTER TABLE gold.game_feature ALTER COLUMN game_instance_key SET NOT NULL;
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS game_feature_instance_key_key
    ON gold.game_feature (game_instance_key);
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS prediction_instance_pkey_idx
    ON gold.prediction (game_instance_key, model_version, generated_at);

ALTER TABLE gold.prediction DROP CONSTRAINT IF EXISTS prediction_pkey;

ALTER TABLE gold.prediction
    ADD CONSTRAINT prediction_pkey
    PRIMARY KEY USING INDEX prediction_instance_pkey_idx;
