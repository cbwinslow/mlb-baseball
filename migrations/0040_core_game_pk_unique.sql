-- An MLB Stats API gamePk identifies one MLB game.  Schedule rows can repeat
-- after postponements or suspended/resumed play, but that history belongs in
-- raw.mlb_schedule and must not produce two canonical core.game rows with the
-- same provider key.  Retrosheet-only games legitimately have no MLB key, so
-- enforce uniqueness only when the value is populated.
CREATE UNIQUE INDEX core_game_game_pk_key
    ON core.game (game_pk)
    WHERE game_pk IS NOT NULL;
