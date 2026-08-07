-- Persistent identity/provenance for game instances.  gold.game_feature is
-- deliberately rebuilt in place, so it cannot be the historical owner of a
-- prediction's game identity.
CREATE TABLE meta.game_instance (
    game_instance_key text PRIMARY KEY,
    identity_kind text NOT NULL CHECK (identity_kind IN ('mlb_schedule', 'retrosheet', 'legacy')),
    season integer,
    game_date date,
    game_number integer,
    mlb_game_pk text,
    retro_game_id text,
    core_game_id bigint,
    first_seen_at timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX game_instance_core_game_key
    ON meta.game_instance (core_game_id) WHERE core_game_id IS NOT NULL;
CREATE INDEX game_instance_mlb_lookup_idx
    ON meta.game_instance (mlb_game_pk);

-- Capture the pre-registry feature population before any later full rebuild.
-- Every feature row already has a non-null key after 0034.  We do not guess a
-- canonical key for legacy rows; their durable legacy key is retained.
INSERT INTO meta.game_instance (
    game_instance_key, identity_kind, season, game_date, game_number,
    mlb_game_pk, retro_game_id, core_game_id
)
SELECT
    f.game_instance_key,
    CASE
        WHEN f.game_instance_key LIKE 'mlb:%' THEN 'mlb_schedule'
        WHEN f.game_instance_key LIKE 'retro:%' THEN 'retrosheet'
        ELSE 'legacy'
    END,
    f.season,
    f.game_date,
    g.game_number,
    f.mlb_game_pk,
    g.retro_game_id,
    f.game_id
FROM gold.game_feature f
LEFT JOIN core.game g ON g.id = f.game_id
ON CONFLICT (game_instance_key) DO UPDATE SET
    core_game_id = COALESCE(EXCLUDED.core_game_id, meta.game_instance.core_game_id),
    retro_game_id = COALESCE(EXCLUDED.retro_game_id, meta.game_instance.retro_game_id),
    last_seen_at = now();
