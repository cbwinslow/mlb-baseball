-- Cluster-wide PostgreSQL 16 tuning for the mlb pipeline -- RESTART-REQUIRED round.
-- Spec: docs/superpowers/specs/2026-08-28-pipeline-performance-design.md (Phase 1.0,
-- "Restart-required, proposed separately").
--
-- This is the companion to scripts/pg_tune.sql. That file holds the reload-only
-- changes (already applied). This file holds the ones that only take effect after
-- a `systemctl restart postgresql@16-main` -- so it is a deliberate maintenance
-- step, run in a quiet window, NOT during the 06:00 daily job.
--
-- SHARED cluster (port 5432): mlb, govdata, promscale, langfuse, and TimescaleDB.
-- shared_buffers / wal_buffers are cluster-wide -- every database benefits from
-- the larger cache; none is harmed. The restart is a ~5-10 second outage for all
-- of them.
--
-- Why these, and why "maybe 10-20%, not a transformation" (measured reasoning in
-- the spec): the box already keeps ~104 GB of file data in the OS page cache, so
-- the hot tables are mostly NOT read cold from the HDDs. The real nightly cost is
-- CPU (rolling-window aggregates over 16.5 M rows) and writing ~30 M rows. These
-- settings help the write side and shave the OS-cache -> shared_buffers copy;
-- they do not remove the rebuild-everything work. That needs the structural
-- change (Phase 3), deferred.
--
--   RAM budget check (125 GB total, ~45 GB in use outside the page cache):
--     shared_buffers 32 GB -> 40 GB  =>  +8 GB pinned, ~72 GB still free for the
--     OS cache + the nightly job's work_mem spikes. The exclusive workflow lock
--     means one big job at a time, so the transient work_mem peak does not stack.
--
-- Run once as a superuser, THEN restart:
--   psql -d mlb -f scripts/pg_tune_restart.sql
--   sudo systemctl restart postgresql@16-main
--   psql -d mlb -f scripts/pg_tune_restart.sql   # re-run: the trailing SELECT
--                                                # now shows pending_restart = f
--
-- Reverse any single setting with:  ALTER SYSTEM RESET <name>;  then restart.

-- ---------------------------------------------------------------------------
-- 1. Bigger caches (take effect on restart)
-- ---------------------------------------------------------------------------

-- 32 GB -> 40 GB. More of the ~22 GB hot working set (Retrosheet events 11 GB,
-- Statcast 10 GB, gold.game_feature 0.6 GB) stays in Postgres's own buffer pool
-- instead of only the OS page cache, removing a memory copy per access.
ALTER SYSTEM SET shared_buffers = '40GB';

-- 16 MB -> 64 MB. The nightly rebuild writes ~30 M rows in big batches; the
-- default 16 MB WAL buffer forces frequent flushes mid-transaction. 64 MB is the
-- effective ceiling (one WAL segment).
ALTER SYSTEM SET wal_buffers = '64MB';

-- Planner hint only (no allocation). Match the box's real cache reality: ~104 GB
-- of page cache observed. Was ~94 GB.
ALTER SYSTEM SET effective_cache_size = '100GB';

-- ---------------------------------------------------------------------------
-- 2. Keep the background writer ahead of the nightly write burst
--    (reload-only -- applies at the next pg_reload_conf(), no restart needed --
--    but grouped here because it targets the same rebuild write path)
-- ---------------------------------------------------------------------------

-- 100 -> 1000 pages per round. During the rebuild the default lets dirty pages
-- pile up until a checkpoint or a backend has to write them synchronously;
-- letting bgwriter clear more per round keeps that work off the query path.
ALTER SYSTEM SET bgwriter_lru_maxpages = 1000;

-- ---------------------------------------------------------------------------
-- 3. autoprewarm: reload the buffer pool on startup so the first post-restart
--    daily run is not slow on cold reads
-- ---------------------------------------------------------------------------

-- ALTER SYSTEM SET on shared_preload_libraries REPLACES the whole value, so the
-- full current list is repeated here with pg_prewarm appended. Verify against
--   SHOW shared_preload_libraries;
-- before applying -- if another entry has been added since this was written,
-- add it here too.
ALTER SYSTEM SET shared_preload_libraries =
    'pg_stat_statements, pg_cron, timescaledb, age, pg_prewarm';

SELECT pg_reload_conf();
SELECT pg_sleep(1);

-- After the restart, once, as a superuser (autoprewarm then handles it every
-- restart after a clean shutdown -- it dumps the buffer list to
-- $PGDATA/autoprewarm.blocks on shutdown and reloads it on startup):
--   CREATE EXTENSION IF NOT EXISTS pg_prewarm;
--   SELECT pg_prewarm('raw.retrosheet_event');
--   SELECT pg_prewarm('raw.statcast_pitch');
--   SELECT pg_prewarm('gold.game_feature');

-- ---------------------------------------------------------------------------
-- Verify. Before the restart these show pending_restart = t for shared_buffers /
-- wal_buffers / shared_preload_libraries. After it, all f.
-- ---------------------------------------------------------------------------
SELECT name, setting, unit, pending_restart
FROM pg_settings
WHERE name IN (
    'shared_buffers', 'wal_buffers', 'effective_cache_size',
    'bgwriter_lru_maxpages', 'shared_preload_libraries'
)
ORDER BY name;

-- ===========================================================================
-- OPTIONAL -- huge pages. Skip unless the two above are measured and you want
-- the next increment. Cuts the CPU's page-table overhead for a 40 GB buffer
-- pool (~10 M 4 KB page entries -> ~20 k 2 MB entries).
--
-- Trade-off: it reserves the RAM up front, usable ONLY by programs that ask for
-- huge pages (Postgres). Get the number wrong high and that RAM is idle; keep
-- huge_pages = try (the current default) so Postgres still starts if the pool
-- is short.
--
--   # 40 GB / 2 MB = 20480, + headroom:
--   echo 'vm.nr_hugepages = 21000' | sudo tee /etc/sysctl.d/60-postgresql-hugepages.conf
--   sudo sysctl --system
--   sudo systemctl restart postgresql@16-main
--   psql -d mlb -c "SHOW huge_pages_status;"   # want: on
--
-- Host currently: vm.nr_hugepages = 512 (1 GB). Raising it to 21000 carves out
-- ~41 GB. Reverse by restoring the file to 512 and re-running sysctl + restart.
-- ===========================================================================
