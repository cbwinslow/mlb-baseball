-- Cluster-wide PostgreSQL 16 tuning for the mlb pipeline.
-- Spec: docs/superpowers/specs/2026-08-28-pipeline-performance-design.md (Phase 1.0).
--
-- This is a SHARED cluster (port 5432): mlb, govdata, promscale, langfuse, ...
-- These are ALL reload-only (no restart). Reverse any single one with
--   ALTER SYSTEM RESET <name>; SELECT pg_reload_conf();
--
-- Run once as a superuser:
--   psql -d mlb -f scripts/pg_tune.sql
--
-- Rationale per setting is in the spec's Phase 1.0 table. The headline: work_mem
-- was 25 MB, so the big enrichment sorts/hashes were spilling to disk (fatal on
-- this cluster's spinning HDDs).

ALTER SYSTEM SET work_mem = '128MB';
ALTER SYSTEM SET hash_mem_multiplier = 3;
ALTER SYSTEM SET maintenance_work_mem = '4GB';
ALTER SYSTEM SET max_parallel_maintenance_workers = 6;
ALTER SYSTEM SET random_page_cost = 2;          -- watch for plan regressions on the other DBs; RESET if any
ALTER SYSTEM SET checkpoint_timeout = '30min';
ALTER SYSTEM SET effective_io_concurrency = 32;

SELECT pg_reload_conf();

-- Verify:
SELECT name, setting, unit, pending_restart
FROM pg_settings
WHERE name IN (
    'work_mem', 'hash_mem_multiplier', 'maintenance_work_mem',
    'max_parallel_maintenance_workers', 'random_page_cost',
    'checkpoint_timeout', 'effective_io_concurrency'
)
ORDER BY name;
