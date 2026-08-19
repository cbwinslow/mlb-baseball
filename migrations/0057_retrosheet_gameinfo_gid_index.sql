-- Raw source tables are deliberately created by their loaders, not migrations
-- (see migration 0039's identical header). A clean clone therefore has no
-- raw.retrosheet_gameinfo yet; conditionally add this index for an existing
-- database and let the loader create it going forward for a first-time table
-- creation (see mlb_baseball/load.py's own scope_column index mechanism --
-- this index is on `gid`, the table's actual downstream join key used by
-- every enrichment SQL file, not `_season`/`_scope`, the loader's own
-- delete-by-chunk key, so it needs its own explicit definition here).
--
-- PR #47 review (CodeAnt/Kilo): this index was applied directly to
-- production `mlb` (2026-08-19, `CREATE INDEX CONCURRENTLY`, see
-- plans/PROGRESS.md's "Production incident found and fixed" entry) without
-- a migration -- correct finding, fixed here so a clean clone, `mlb_test`,
-- and a restored production database all reproduce the same schema.
DO $$
BEGIN
    IF to_regclass('raw.retrosheet_gameinfo') IS NOT NULL THEN
        CREATE INDEX IF NOT EXISTS idx_retrosheet_gameinfo_gid
            ON raw.retrosheet_gameinfo (gid);
    END IF;
END $$;
