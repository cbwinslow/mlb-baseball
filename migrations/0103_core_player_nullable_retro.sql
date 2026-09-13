-- Retrosheet assigns a player's `key_retro` only months after a season ends,
-- once it has processed that season's event files. Chadwick assigns `key_mlbam`
-- immediately from MLBAM source records. So every current-season debut and
-- call-up exists in `raw.register_people` with an MLBAM id but no Retrosheet id
-- -- and `conform_player_insert.sql` (which filters `WHERE key_retro IS NOT
-- NULL`) drops them from `core.player` entirely. Verified 2026-09-07 against
-- production `mlb`: 105 distinct players in 2026 regular-season box scores did
-- not resolve. This is normal upstream behaviour -- pybaseball / baseballr
-- return `key_retro = NaN` for recent debuts and consumers key on what they
-- have.
--
-- Dropping NOT NULL lets conform admit those players on their MLBAM id. The
-- UNIQUE (retro_id) constraint (`player_retro_id_key`) stays: PostgreSQL allows
-- multiple NULLs in a UNIQUE column, so a real `key_retro` is still enforced
-- unique once Retrosheet assigns one. This mirrors migration 0045, which did
-- the same for `core.game.retro_game_id` when MLB-only games arrived.
--
-- Forward-only. `_build_players` is a full truncate-and-rebuild every
-- `mlb conform` (core.player is emptied by conform.run()'s one consolidated
-- TRUNCATE), so a NULL `retro_id` backfills automatically on the next full
-- conform run once `raw.register_people` carries the real `key_retro` -- no
-- data migration and no upsert here.
ALTER TABLE core.player
    ALTER COLUMN retro_id DROP NOT NULL;

COMMENT ON COLUMN core.player.retro_id IS
    'Retrosheet player id. NULL for a current-season player admitted on their '
    'MLBAM id before Retrosheet has processed that season; it backfills on the '
    'next full conform run once raw.register_people carries the real key_retro. '
    'UNIQUE across its non-NULL values.';
