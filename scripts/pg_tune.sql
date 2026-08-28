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

-- Make the planner actually pick parallel plans for the big enrichment
-- aggregations. Measured 2026-08-28: COM-01's core aggregation over
-- raw.statcast_pitch (13.5M rows) went ~60s single-threaded -> ~5s with a
-- 7-worker parallel seq scan. Defaults (setup 1000 / tuple 0.1) were high
-- enough that the planner kept choosing the serial plan.
ALTER SYSTEM SET parallel_setup_cost = 200;
ALTER SYSTEM SET parallel_tuple_cost = 0.05;

SELECT pg_reload_conf();

-- The reload is async — the postmaster signals backends and there is a brief
-- delay before this session sees the new values. Wait, then verify.
SELECT pg_sleep(1);

SELECT name, setting, unit, pending_restart
FROM pg_settings
WHERE name IN (
    'work_mem', 'hash_mem_multiplier', 'maintenance_work_mem',
    'max_parallel_maintenance_workers', 'random_page_cost',
    'checkpoint_timeout', 'effective_io_concurrency',
    'parallel_setup_cost', 'parallel_tuple_cost'
)
ORDER BY name;
