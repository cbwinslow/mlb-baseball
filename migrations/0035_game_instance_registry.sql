-- Persistent identity/provenance for game instances.  gold.game_feature is
-- deliberately rebuilt in place, so it cannot be the historical owner of a
-- prediction's game identity.
--
-- Schema only, deliberately: this must exist before the owner-invoked
-- `mlb backfill-game-identities` command runs (it uses this registry as the
-- authority for assigning game_instance_key values) and before 0036 cuts
-- over the prediction primary key. It does not seed itself from
-- gold.game_feature -- at this point in a fresh replay game_instance_key is
-- still nullable and largely unpopulated (0034), so seeding here would read
-- mostly-empty data instead of being the backfill's source of truth. Seeding
-- is the backfill command's job, not this migration's.
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
