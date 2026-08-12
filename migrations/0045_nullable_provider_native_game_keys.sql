-- MLB-only canonical games have an MLB gamePk but no Retrosheet game ID.
-- A provider-native key must stay NULL when that provider did not supply one;
-- `MLB` + gamePk was a fabricated compatibility value, not source data.
ALTER TABLE core.game
    ALTER COLUMN retro_game_id DROP NOT NULL;

-- This migration is forward-only.  It corrects rows built by earlier versions
-- without touching genuine Retrosheet IDs or any raw/source history.
UPDATE core.game
SET retro_game_id = NULL
WHERE game_pk IS NOT NULL
  AND retro_game_id = 'MLB' || game_pk;
