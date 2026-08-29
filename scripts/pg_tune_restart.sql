\set ON_ERROR_STOP on
-- Cluster-wide PostgreSQL 16 tuning for the mlb pipeline -- RESTART-REQUIRED round.
-- Spec: docs/superpowers/specs/2026-08-28-pipeline-performance-design.md (Phase 1.0,
-- "Restart-required round").
--
-- Companion to scripts/pg_tune.sql (reload-only, already applied). This file has
-- two settings that only take effect after a restart of the PG16 cluster, plus
-- two reload-only ones grouped here because they target the same nightly-rebuild
-- write path.
--
--   RESTART-REQUIRED (PGC_POSTMASTER): shared_buffers, wal_buffers
--   RELOAD-ONLY (apply at pg_reload_conf(), no downtime): effective_cache_size,
--       bgwriter_lru_maxpages
--
-- SHARED cluster (port 5432): mlb, govdata, promscale, langfuse, TimescaleDB.
-- shared_buffers / wal_buffers are cluster-wide -- every database gets the larger
-- cache. effective_cache_size is a planner *hint* (no allocation) that affects
-- cost estimates in every database: a +6% bump (94 -> 100 GB) is very unlikely to
-- flip a plan, but if a non-mlb workload regresses after this, that is the one to
-- suspect -- `ALTER SYSTEM RESET effective_cache_size; SELECT pg_reload_conf();`
-- reverses it with no restart.
--
-- Honest expectation: an UNVALIDATED ~10-20% estimate, not measured for this
-- round (scripts/pg_tune.sql's numbers were work_mem + parallelism). The box
-- already holds ~104 GB of file data in the OS page cache, so the hot tables are
-- rarely read cold; the real nightly cost is CPU (rolling-window aggregates over
-- 16.5 M rows) and the ~30 M-row rebuild write. Those need the structural change
-- (Phase 3), deferred by owner decision. Record before/after nightly `conform` +
-- `predict` wall-clock when you apply this.
--
--   RAM budget (125 GB total, ~45 GB in use outside the page cache):
--     shared_buffers 32 -> 40 GB  =>  +8 GB pinned, ~72 GB still free for the OS
--     cache + the nightly job's work_mem spikes. The `exclusive` workflow lock
--     means one big job at a time, so the transient work_mem peak does not stack.
--
-- RUNBOOK (run in a quiet window -- no predict/conform running, not near 06:00):
--   psql -X -v ON_ERROR_STOP=1 -d mlb -f scripts/pg_tune_restart.sql
--   sudo systemctl restart postgresql@16-main
--   psql -X -v ON_ERROR_STOP=1 -d mlb -f scripts/pg_tune_restart.sql   # re-run:
--       # the trailing SELECT now shows pending_restart = f for both restart rows
--   # then, once (operational, not schema -- like the restart itself):
--   psql -X -d mlb -c "CREATE EXTENSION IF NOT EXISTS pg_prewarm; \
--     SELECT relname, pg_prewarm(oid) FROM pg_class \
--     WHERE oid IN ('raw.retrosheet_event'::regclass, \
--                   'raw.statcast_pitch'::regclass, 'gold.game_feature'::regclass);"
--
-- ROLLBACK:
--   restart-required rows:  ALTER SYSTEM RESET shared_buffers;
--                           ALTER SYSTEM RESET wal_buffers;   then restart.
--   reload-only rows:       ALTER SYSTEM RESET effective_cache_size;
--                           ALTER SYSTEM RESET bgwriter_lru_maxpages;
--                           SELECT pg_reload_conf();          -- no restart.
--   (shared_preload_libraries is deliberately NOT touched by this script -- an
--   ALTER SYSTEM SET there replaces the whole list and a missing/typo'd module
--   stops the cluster from starting. Leave it to a dedicated, reviewed change.)

-- ---------------------------------------------------------------------------
-- Restart-required
-- ---------------------------------------------------------------------------

-- 32 GB -> 40 GB. More of the ~22 GB hot working set (Retrosheet events 11 GB,
-- Statcast 10 GB, gold.game_feature 0.6 GB) stays in Postgres's own buffer pool
-- instead of only the OS page cache, removing a memory copy per access.
ALTER SYSTEM SET shared_buffers = '40GB';

-- 16 MB -> 64 MB (= 4 x the 16 MB wal_segment_size on this cluster). The nightly
-- rebuild writes ~30 M rows in large batches; a bigger WAL buffer means fewer
-- premature flushes while a batch is still filling. 64 MB is a common value for a
-- write-heavy cluster; not benchmarked here -- revert to 16 MB if a write test
-- shows no benefit.
ALTER SYSTEM SET wal_buffers = '64MB';

-- ---------------------------------------------------------------------------
-- Reload-only (no restart; grouped here for context)
-- ---------------------------------------------------------------------------

-- Planner hint only. Match the box's real cache reality: ~104 GB of page cache
-- observed on prod 2026-08-29. Was ~94 GB.
ALTER SYSTEM SET effective_cache_size = '100GB';

-- 100 -> 1000 pages per round. During the rebuild the default lets dirty pages
-- pile up until a checkpoint or a backend has to write them synchronously;
-- clearing more per round keeps that work off the query path.
ALTER SYSTEM SET bgwriter_lru_maxpages = 1000;

SELECT pg_reload_conf();
SELECT pg_sleep(1);

-- Verify. Before the restart, shared_buffers and wal_buffers show
-- pending_restart = t; the two reload-only rows are already f. After the
-- restart, all f.
SELECT name, setting, unit, pending_restart
FROM pg_settings
WHERE name IN (
    'shared_buffers', 'wal_buffers', 'effective_cache_size', 'bgwriter_lru_maxpages'
)
ORDER BY name;

-- ===========================================================================
-- OPTIONAL -- huge pages. Skip unless the two restart-required settings are
-- measured and you want the next increment. Cuts the CPU's page-table overhead
-- for a 40 GB buffer pool.
--
-- Do NOT hardcode the page count. After `shared_buffers = 40GB` is live, ask
-- Postgres how many it needs (it accounts for the whole main shared-memory area,
-- not just shared_buffers, at the host's huge_page_size):
--
--   psql -X -d mlb -c "SHOW shared_memory_size_in_huge_pages;"   # e.g. ~20700
--   grep -E 'Hugepagesize|HugePages_Total' /proc/meminfo         # confirm 2 MB
--
-- Then reserve that many + ~5% headroom, keeping huge_pages = try so a short
-- pool cannot block startup:
--
--   echo 'vm.nr_hugepages = <count>' | sudo tee /etc/sysctl.d/60-postgresql-hugepages.conf
--   sudo sysctl --system
--   sudo systemctl restart postgresql@16-main
--   psql -X -d mlb -c "SHOW huge_pages_status;"   # want: on
--
-- Host currently: vm.nr_hugepages = 512 (1 GB). Reverse by restoring the file to
-- 512 and re-running sysctl + restart.
-- ===========================================================================
