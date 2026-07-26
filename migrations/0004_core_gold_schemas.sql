-- Renames "conformed" to "core" (shorter, matches the naming convention in
-- CLAUDE.md, and matches what the old project's own real SQL migrations
-- used for the same concept, not just its docs) and adds "gold" as the
-- third medallion layer. See docs/DECISIONS.md ADR-013.
--
-- ALTER SCHEMA is a safe rename, not a drop/recreate: "conformed" has had
-- zero tables in it since it was created in 0001_init.sql, so there is
-- nothing to migrate.
ALTER SCHEMA conformed RENAME TO core;

-- Created now so the shape is right going forward and nothing needs
-- renaming later, but deliberately left empty — no gold tables until
-- Phase 2 (ML modeling) or Phase 3 (website) actually need them. See
-- docs/NORTH_STAR.md: don't design a later phase's architecture early.
CREATE SCHEMA IF NOT EXISTS gold;
