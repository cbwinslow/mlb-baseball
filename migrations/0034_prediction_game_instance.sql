-- A game_pk is useful for MLB-API lookups but is not a globally unique game
-- instance identifier: real suspended/resumed games can share it.  Preserve
-- it as an attribute and give feature/prediction rows an explicit durable key.
--
-- This is schema preparation only. The owner-invoked, resumable
-- `mlb backfill-game-identities` command performs the data backfill before
-- 0035 may cut over the prediction primary key.

ALTER TABLE gold.game_feature ADD COLUMN IF NOT EXISTS game_instance_key text;
ALTER TABLE gold.prediction ADD COLUMN IF NOT EXISTS game_instance_key text;
