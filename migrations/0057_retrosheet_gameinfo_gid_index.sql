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
--
-- Non-CONCURRENTLY, on purpose, not an oversight (real finding from the
-- same review round, verified directly against real Postgres): a DO block
-- is PL/pgSQL, and `CREATE INDEX CONCURRENTLY cannot be executed from a
-- function` -- confirmed by actually running it inside one and reading the
-- real error, not assumed. The conditional table-existence guard above
-- (needed since raw.retrosheet_gameinfo is loader-created, not always
-- present) and CONCURRENTLY are mutually exclusive; migration 0039 has the
-- identical constraint for the same reason and made the same choice. On a
-- clean clone this is a no-op (table doesn't exist yet). On `mlb_test` or a
-- restored production snapshot where the table already has real rows,
-- applying this migration *will* briefly take an ACCESS EXCLUSIVE lock on
-- raw.retrosheet_gameinfo for the index build -- acceptable here since
-- `mlb migrate` runs as a deliberate maintenance step against a
-- non-latency-sensitive raw ingestion table, not concurrently with live
-- traffic, matching this codebase's existing precedent for this exact
-- tradeoff. Production `mlb` itself already has the index (applied via
-- CONCURRENTLY before this migration existed, see above) so this specific
-- migration only ever locks anything on a *different* environment that
-- doesn't have it yet.
DO $$
BEGIN
    IF to_regclass('raw.retrosheet_gameinfo') IS NOT NULL THEN
        CREATE INDEX IF NOT EXISTS idx_retrosheet_gameinfo_gid
            ON raw.retrosheet_gameinfo (gid);
    END IF;
END $$;
