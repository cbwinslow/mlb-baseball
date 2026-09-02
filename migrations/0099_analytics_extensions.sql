-- Makes a small set of contrib extensions AVAILABLE for later research-query
-- and identity-matching work. This migration only runs CREATE EXTENSION --
-- it adds no indexes and changes no table. Indexes and queries that use
-- these ship in the migration that introduces their consumer.
--
--   pg_trgm    -- trigram similarity, for fuzzy player/team name crosswalking
--                (the ~0.5% unresolved MLBAM-id gap + mojibake names). NOT for
--                conformance -- conformance stays exact-match (ADR-029).
--   unaccent   -- accent-insensitive text ("Jose" == "José") for research
--                search; pairs with pg_trgm.
--   btree_gist -- scalar types in GiST, for temporal/range EXCLUDE constraints
--                if a future schema needs one.
--   tablefunc  -- crosstab() for ad-hoc multi-season / platoon matrix pivots
--                in research queries (the pipeline's own pivots stay
--                `COUNT(*) FILTER (...)`, which needs no extension).
--
-- pgvector (`vector`) is deliberately NOT enabled here: ADR-279 gates it on a
-- named, rights-approved embedding feature and a similarity-search consumer,
-- neither of which exists yet. Add `CREATE EXTENSION vector` in the migration
-- that introduces that consumer.

CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;
CREATE EXTENSION IF NOT EXISTS btree_gist;
CREATE EXTENSION IF NOT EXISTS tablefunc;
