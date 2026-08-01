-- pg_stat_statements is already loaded via shared_preload_libraries on this
-- cluster (confirmed: `SHOW shared_preload_libraries`), but CREATE
-- EXTENSION is still required per-database -- it wasn't present in either
-- mlb or mlb_test until now. This is what makes real query-timing
-- investigations possible (see docs/DECISIONS.md ADR-043) and what
-- mlb doctor's new pg_stat_statements check depends on.
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
