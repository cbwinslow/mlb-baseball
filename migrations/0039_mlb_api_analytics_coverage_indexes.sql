-- Raw source tables are deliberately created by their loaders, not migrations.
-- A clean clone therefore has no analytics tables yet; conditionally add these
-- indexes for an existing database and let a later loader create its ordinary
-- scope indexes when it creates a table for the first time.
DO $$
BEGIN
    IF to_regclass('raw.mlb_win_prob') IS NOT NULL THEN
        CREATE INDEX IF NOT EXISTS mlb_win_prob_season_game_idx
            ON raw.mlb_win_prob (_season, game_pk);
    END IF;
    IF to_regclass('raw.mlb_linescore') IS NOT NULL THEN
        CREATE INDEX IF NOT EXISTS mlb_linescore_season_game_idx
            ON raw.mlb_linescore (_season, game_pk);
    END IF;
    IF to_regclass('raw.mlb_game_context') IS NOT NULL THEN
        CREATE INDEX IF NOT EXISTS mlb_game_context_season_game_idx
            ON raw.mlb_game_context (_season, game_pk);
    END IF;
END $$;
