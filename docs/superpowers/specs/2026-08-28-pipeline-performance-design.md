# Pipeline & test performance: make `conform`/`predict` fast and crash-safe

**Status:** Design spec, not yet an implementation plan. Written via `superpowers:brainstorming`
on 2026-08-28 with the project owner.

## Why this spec exists

The daily `mlb predict` job (cron `scripts/mlb_daily_update.sh`, 06:00 UTC) **has failed every
morning since ~2026-08-21.** `gold.prediction` was last generated **2026-08-20**. The most recent
failure (2026-08-27) was `psycopg.OperationalError: the connection is lost` partway through
`conform.run()`.

Root causes, measured against real production `mlb` on 2026-08-28 (not assumed):

1. **`mlb predict` runs as one ~5-hour transaction holding an exclusive workflow lock.**
   `model.run()` opens one non-autocommit connection under `track_run(..., workflow="exclusive")`
   and inside it runs `build_feature_stage()` → `enrich_feature_stage()` (33 sequential module
   calls) → `elo.compute_ratings()` → `diff.compute()` → predictions. A dropped connection at any
   point rolls back **everything** — 5 hours of work lost, nothing committed, lock released only by
   crash recovery.
2. **`gold.leverage_index` is pathological.** `pg_stat_statements`: **228 calls, 29,111 s
   cumulative, 127 s mean.** It is a near-static reference table (real historical WE-swing per
   base/out state, ADR-262) built by a per-season Python loop that re-runs a heavy aggregation for
   every season on every run.
3. **`conform` rebuilds all ~129 seasons from raw every run.** `TRUNCATE core.play, core.pitch,
   core.game, gold.game_feature, …` appears 62× in the stats; individual point-in-time enrichment
   queries (COM-01 "strike zone command", SHP-01 "pitch movement") take **14–18 minutes each**.
4. **Missing indices on the hot raw tables.** `raw.retrosheet_event` (16.5M rows) is indexed only
   on `game_id` — nothing on `pit_id` / `bat_id`. `raw.statcast_pitch` (13.5M rows) — nothing on
   `pitcher` / `batter`. Point-in-time "entering metrics per pitcher" queries seq-scan the full
   table on spinning disk.
5. **Hardware:** 40 cores, 125 GB RAM, Postgres 16.15, `shared_buffers` 32 GB, `effective_cache_size`
   96 GB, parallel workers ≤ 40. **All six disks are rotational SAS HDDs** (no SSD); PG data on
   `/mnt/storage/postgres-data`. Postgres is *not* CPU- or RAM-starved. The bottleneck is disk
   random I/O + rebuild-everything design + the two pathological areas above.
6. **Machine contention:** ~40 other cron jobs (sysmon) fire every 1–5 min plus the every-5-min
   `mlb_api_update`. Load average was 13.5 during investigation.

## Goals

- Daily `mlb predict` completes reliably in **well under 1 hour**, and a mid-run failure loses
  minutes, not hours (checkpointed progress).
- A single `conform` or `predict` invocation is cheap enough to iterate on during development.
- Full integration test suite runs in **≤ 5 minutes** (currently ~52 min on CI).
- Every change is measured before/after (`pg_stat_statements`, `EXPLAIN (ANALYZE, BUFFERS)`,
  wall-clock) — no "should be faster" claims without a number.

## Non-goals (this spec)

- Migrating production to the Postgres 17 instance on port 5434 (real upside — PG17 streaming I/O
  for seq scans helps HDDs — but it's its own migration project; tracked as a follow-up issue,
  not done here).
- Rewriting the sabermetric logic of any enrichment module (that's the separate metrics-layer
  work). This spec only changes *how often* and *in what transaction shape* they run.
- Buying SSDs or changing hosting ($0/month constraint).

## Phase 1 — quick wins, no restructure (target: 5h → ~1h, tests → ~10 min)

Each item ships as its own commit with a measured before/after in the message.

### 1.1 Cache `gold.leverage_index` / `gold.win_expectancy`

These are historical reference tables that only change when a *completed* season's games change.
`leverage_index.compute()` / `win_expectancy.compute()` should:
- Check a stored fingerprint (max `game_date` + row count of the source, per season).
- Recompute **only** seasons whose fingerprint changed (in practice: the current season, plus any
  season touched by a backfill).
- Be a true no-op (single `SELECT` of the fingerprint) when nothing changed.

Expected: 29,111 s cumulative → seconds on a normal daily run.

### 1.2 Per-session durability/memory pragmas for the rebuild

`conform` and `model.run()` rebuild from a reproducible source — a crash just means re-run. At the
start of those sessions (not globally), `SET LOCAL`:
- `synchronous_commit = off`
- `work_mem = 512MB` (big window/sort/hash ops currently spill to disk at 25 MB — fatal on HDD)
- `maintenance_work_mem = 4GB` (index builds, `VACUUM`)
- consider `jit = off` already set globally; leave it.

This mirrors the **already-proven** test-DB pattern (`tests/conftest.py::_speed_up_test_database`,
measured bulk `TRUNCATE` 79–84 s → ~20 s).

### 1.3 Targeted indices on raw tables — validated with `hypopg` first

Install `hypopg` (hypothetical indexes — test benefit without paying the multi-hour build on HDD).
For each 14–18 min enrichment query: `EXPLAIN` with hypothetical indexes on candidate keys
(`raw.retrosheet_event(pit_id)`, `(bat_id)`, `(pit_id, game_id)`; `raw.statcast_pitch(pitcher)`,
`(batter)`, `(pitcher, game_date)`). Build **only** the ones that change the plan and the measured
time. Document each in a migration with the before/after `EXPLAIN`. Reject any that don't earn
their keep (every index slows the COPY ingestion path).

### 1.4 `mlb_test` on tmpfs + `fsync=off`

The test database is disposable (`_assert_test_database_url` guarantees it can't be `mlb`). Run its
Postgres cluster with the data directory on tmpfs, or `fsync=off` / `full_page_writes=off` for that
cluster. Combined with the existing `UNLOGGED` partitions + `synchronous_commit=off`, this removes
disk from the test loop entirely. Wire into `pytest-postgresql`'s `postgresql_noproc` setup.

### 1.5 `pytest-xdist` with schema/database-per-worker

Add `pytest-xdist`; each worker clones its own database from the pre-migrated template (the
conftest already builds one via `postgresql_noproc`). Target: 563 integration tests across 8–12
workers. Fixes the wall-clock; the fixture-ordering bugs (#78, #58, #56, #67) must be fixed in the
same effort or xdist will surface them as flakes.

### 1.6 Diagnostic extensions

`CREATE EXTENSION` on `mlb` (all low-risk, reversible): `hypopg`, `pg_prewarm` (warm
`shared_buffers` after restart so first queries aren't cold HDD reads), `pg_buffercache`,
`pgstattuple`, `pg_stat_kcache`. Add a `mlb doctor` check that flags "predictions stale > 36h".

## Phase 2 — reliability restructure (crash-safe, decoupled)

### 2.1 Break the one 5-hour transaction into checkpointed stages

`model.run()` should commit after each major stage (base build, each enrichment group, elo, diff,
predictions) and record progress in a `meta` table. A dropped connection resumes from the last
committed checkpoint instead of restarting. The workflow lock is re-acquired per stage, not held
for the whole run.

### 2.2 Decouple `predict` from `conform`

`scripts/mlb_daily_update.sh` currently runs `update && conform && predict` under one `flock`, and
`set -e` means a `conform` hiccup skips `predict` entirely. Give `predict` its own lock and its own
scheduled entry that runs if `conform` produced a fresh-enough `core.game`, with its own failure
logging. One failing does not silently block the other.

### 2.3 Parallelize independent enrichment modules

`enrich_feature_stage()`'s 33 calls are mostly independent (the ordering constraints are
documented per-line: `age` last, `diff` after `elo`, live/probable after their historical variant).
Group into a dependency DAG and run independent groups concurrently on separate pooled connections.
Needs 2.4.

### 2.4 PgBouncer (connection management)

Adopt PgBouncer in transaction-pooling mode as the single front door for: the parallel enrichment
workers (2.3), the every-5-min `mlb_api_update`, and concurrent test/agent runs. This is the
established tool for "Postgres handling many operations" — do not hand-roll pooling. Document the
`mlb`-vs-`mlb_test` routing explicitly.

## Phase 3 — incremental pipeline (stop reprocessing dead seasons)

The structural fix: only today's games change. `conform` and the enrichment SQL should process
**changed games only**, not truncate-and-rebuild 129 seasons nightly.

- Adopt SQLMesh incremental models for `core` conform + `gold` enrichment (ADR-088 direction;
  issue #70 "SQLMesh catch-up: adopt for model/" already tracks this). SQLMesh's
  `INCREMENTAL_BY_TIME_RANGE` / `INCREMENTAL_BY_UNIQUE_KEY` kinds fit game-grain data directly.
- Keep a `--full-rebuild` escape hatch for backfills and schema changes.
- Full-rebuild remains the tested path in CI (correctness); incremental is validated against it
  (a full rebuild and an incremental catch-up must produce identical `gold.game_feature`).

## Extensions & tooling evaluation (informs the phases above)

**Already installed on `mlb` (PG16):** `age`, `btree_gist`, `citext`, `pg_cron`,
`pg_stat_statements`, `pg_trgm`, `pgcrypto`, `plpython3u`, `postgis`, `tablefunc`, `timescaledb`
2.28, `uuid-ossp`, `vector` (pgvector) 0.8. (So PR #74's proposed adds are mostly redundant —
close or trim it.)

**Add now (Phase 1):** `hypopg`, `pg_prewarm`, `pg_buffercache`, `pgstattuple`, `pg_stat_kcache` —
diagnostics + index validation.

**Evaluate, decide with evidence (not in Phase 1):**
- **`timescaledb` hypertables for `raw.statcast_pitch` (13.5M) and `raw.mlb_win_prob` (12.6M).**
  Native compression (often 90%+ on this shape) and fast time-range scans. Cost: partitioning
  column must be in the PK; some query/`COPY` patterns change; the connectors' upsert logic needs
  review. Worth a spike with a real before/after on the slow enrichment queries.
- **`pg_partman`** to automate the existing `core.play` / `core.pitch` season partitioning
  (currently hand-managed — `play_pkey ON ONLY core.play`).
- **`pg_repack`** to de-bloat `core`/`gold` after big rebuilds without long locks.
- **pgvector** is installed but unused — real fit for the `raw.news` NLP corpus (semantic dedup /
  similarity) once that feature work starts; note for the metrics-layer arc, not here.

**Postgres 17 (port 5434):** real upside for this HDD-bound workload (PG17 streaming I/O for
sequential scans, better parallel-scan scheduling, faster `VACUUM`). But it's a 55 GB data
migration + revalidating every connector, migration, and test against a new major version.
Separate follow-up issue; revisit after Phase 1–2 land and we know how much headroom remains.

## Testing strategy

- Every Phase 1 perf change: a committed before/after measurement (query time from
  `pg_stat_statements` or `EXPLAIN (ANALYZE, BUFFERS)`; suite wall-clock for test changes).
- `leverage_index` / `win_expectancy` caching (1.1): an integration test proving (a) a second call
  with unchanged source is a no-op (0 rows written, sub-second), (b) a changed season triggers
  exactly that season's recompute, (c) the cached result is byte-identical to a forced full
  rebuild.
- Checkpointing (2.1): an integration test that kills the connection mid-run and asserts the next
  run resumes from the last checkpoint (same pattern as
  `test_ingest_tracking.py::test_failure_path_logs_error_and_leaves_connection_usable`).
- Incremental (3): the full-vs-incremental equivalence test described in Phase 3.
- No production writes from any test; `mlb_test` only; `_assert_test_database_url` unchanged.

## Rollout

1. Phase 1 lands as small PRs, each independently revertable. After 1.1 + 1.2, re-enable the daily
   cron and watch a real run reach "finished daily update".
2. Backfill the 8 days of missing predictions with one supervised `mlb predict` run
   (`DATABASE_URL=postgresql:///mlb` stated explicitly, owner-authorized) once Phase 1 makes it
   an hour, not five.
3. Phase 2 and 3 follow as separate specs/plans if this one gets too large to execute as a unit.

## Open questions for the owner

1. OK to run `mlb_test`'s cluster with `fsync=off` / on tmpfs? (Safe — disposable DB — but worth a
   yes.)
2. PgBouncer: acceptable to add as a system service, or prefer application-side pooling
   (`psycopg_pool`) to keep the deploy simpler?
3. Priority order if Phase 1 is still too slow to iterate: push straight to Phase 3 (incremental)
   for `conform`, or finish Phase 2 (reliability) first?
