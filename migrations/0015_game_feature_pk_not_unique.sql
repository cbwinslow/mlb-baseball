-- gold.game_feature.mlb_game_pk can't be a hard UNIQUE constraint after
-- all -- found running mlb predict against real production data: MLB's
-- own schedule data genuinely reuses one game_pk (123347) across two
-- different core.game rows for a real 1944 suspended-and-resumed game
-- (documented in conform.py's _backfill_game_pk comments, and already
-- why core.game.game_pk itself has only a plain index, not a UNIQUE
-- constraint -- this migration brings gold.game_feature in line with
-- that same, already-established precedent rather than reinventing it.

DROP INDEX gold.game_feature_mlb_game_pk_key;
CREATE INDEX game_feature_mlb_game_pk_idx ON gold.game_feature (mlb_game_pk);
