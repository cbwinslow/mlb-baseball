-- The original 0034--0036 identity cutover assumed a suspended or resumed
-- MLB game could be a second game instance. Verified provider documentation
-- establishes that game_pk remains the one MLB game identity; schedule dates
-- are source-history observations. Keep the compatibility column, but make
-- its MLB value canonical (mlb:<game_pk>) and retain old schedule-shaped
-- registry records as explicit legacy provenance.

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM gold.game_feature
        WHERE mlb_game_pk IS NOT NULL
        GROUP BY mlb_game_pk
        HAVING count(*) > 1
    ) THEN
        RAISE EXCEPTION
            'cannot canonicalize gold.game_feature: duplicate populated mlb_game_pk values exist; inspect and rebuild features first';
    END IF;
    IF EXISTS (
        SELECT 1
        FROM gold.prediction
        GROUP BY mlb_game_pk, model_version, generated_at
        HAVING count(*) > 1
    ) THEN
        RAISE EXCEPTION
            'cannot canonicalize gold.prediction: duplicate MLB-game/model/timestamp rows exist; inspect before migration';
    END IF;
END $$;

ALTER TABLE meta.game_instance
    DROP CONSTRAINT IF EXISTS game_instance_identity_kind_check;

-- Old registry rows are retained for traceability but cannot be mistaken for
-- canonical MLB identities. A canonical row is added below for each provider
-- key already represented in the registry.
UPDATE meta.game_instance
SET identity_kind = 'legacy'
WHERE identity_kind = 'mlb_schedule';

ALTER TABLE meta.game_instance
    ADD CONSTRAINT game_instance_identity_kind_check
    CHECK (identity_kind IN ('mlb_game', 'retrosheet', 'legacy'));

INSERT INTO meta.game_instance (
    game_instance_key, identity_kind, season, game_date, game_number,
    mlb_game_pk, retro_game_id, core_game_id
)
SELECT DISTINCT ON (mlb_game_pk)
    'mlb:' || mlb_game_pk,
    'mlb_game',
    season,
    game_date,
    game_number,
    mlb_game_pk,
    retro_game_id,
    NULL
FROM meta.game_instance
WHERE mlb_game_pk IS NOT NULL
ORDER BY mlb_game_pk, first_seen_at, game_instance_key
ON CONFLICT (game_instance_key) DO UPDATE
SET identity_kind = 'mlb_game',
    season = COALESCE(meta.game_instance.season, EXCLUDED.season),
    game_date = COALESCE(meta.game_instance.game_date, EXCLUDED.game_date),
    game_number = COALESCE(meta.game_instance.game_number, EXCLUDED.game_number),
    mlb_game_pk = COALESCE(meta.game_instance.mlb_game_pk, EXCLUDED.mlb_game_pk),
    retro_game_id = COALESCE(meta.game_instance.retro_game_id, EXCLUDED.retro_game_id),
    last_seen_at = now();

UPDATE gold.game_feature
SET game_instance_key = 'mlb:' || mlb_game_pk
WHERE mlb_game_pk IS NOT NULL
  AND game_instance_key IS DISTINCT FROM 'mlb:' || mlb_game_pk;

UPDATE gold.prediction
SET game_instance_key = 'mlb:' || mlb_game_pk
WHERE game_instance_key IS DISTINCT FROM 'mlb:' || mlb_game_pk;

ALTER TABLE gold.prediction DROP CONSTRAINT IF EXISTS prediction_pkey;
ALTER TABLE gold.prediction
    ADD CONSTRAINT prediction_pkey PRIMARY KEY (mlb_game_pk, model_version, generated_at);

DROP INDEX IF EXISTS gold.game_feature_mlb_game_pk_idx;
CREATE UNIQUE INDEX IF NOT EXISTS game_feature_mlb_game_pk_key
    ON gold.game_feature (mlb_game_pk) WHERE mlb_game_pk IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS game_instance_canonical_mlb_key
    ON meta.game_instance (mlb_game_pk)
    WHERE identity_kind = 'mlb_game' AND mlb_game_pk IS NOT NULL;
