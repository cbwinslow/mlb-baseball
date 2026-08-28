# Pipeline & test performance: make `conform`/`predict` fast and crash-safe

**Status:** Design spec, not yet an implementation plan. Written via `superpowers:brainstorming`
on 2026-08-28 with the project owner.

## Why this spec exists

The daily job (cron `scripts/mlb_daily_update.sh`, 06:00 UTC — `mlb update && mlb conform && mlb
predict`) **has not completed since 2026-08-20.** `gold.prediction` was last generated
**2026-08-20 06:56**. Eight days of stale predictions.

Findings, measured against real production `mlb` + the real cron log on 2026-08-28 (corrected after
a first pass overstated several numbers — validation matters):

1. **A *successful* run takes ~1 hour, not 5.** Real log windows: ~17–23 min in late July, growing
   to ~1h05m–1h21m through mid-August as enrichment modules were added (Aug 18: 1h04m; Aug 20:
   1h14m). The owner's "~5 hours" was likely a stuck/hung run observed, not steady state.
2. **The runs since Aug 21 die during `mlb update` (ingestion) — before `conform`/`predict` ever
   start.** Aug 21–24: the process just stops mid-`statcast_leaderboard` with no Python traceback
   (killed by signal — OOM, reboot, or an external `kill`; load average was 13.5). Contributing:
   `[mlb_api] FAILED (mlb_api: another ingestion run is already active)` every run — the every-5-min
   `mlb_api_update` cron holds a lock the daily `mlb update`'s `mlb_api` step can't get; and Kalshi
   `429 Too Many Requests` retry stalls. Aug 25–27 runs additionally hit the `bsr.py` `gdp_fl`
   column bug (**now fixed on main**, ADR-260) once they got as far as `predict`.
3. **`mlb predict`, when it does run, is one long transaction holding an exclusive workflow lock.**
   `model.run()` runs `build_feature_stage()` → `enrich_feature_stage()` (33 sequential module
   calls) → `elo.compute_ratings()` → `diff.compute()` → predictions on one non-autocommit
   connection. A drop anywhere rolls back the whole ~40+ min of feature work — nothing checkpointed.
4. **The individual enrichment queries are genuinely slow** (`pg_stat_statements`, 13-day window):
   COM-01 "strike zone command" **1,070 s**, SHP-01 "pitch movement" **859 s**, "expected
   resolvable starter ERA" **215 s mean ×8**, RE24/LI entering-game **344 s**. Each runs over the
   full freshly-rebuilt `gold.game_feature` every time (no incrementality).
5. **`gold.leverage_index` is a latent risk, not a current daily cost.** `pg_stat_statements` shows
   228 calls / 29,111 s cumulative — but that's ~2 full rebuilds' worth of dev churn over 13 days.
   `compute()` has a working "build once if empty, else no-op" guard and `conform` does **not**
   truncate it. The risk: *if* the table is ever cleared, the next daily run does a 4.5-hour
   per-season rebuild inline. Worth hardening (incremental for the current season), not the fire.
6. **Missing indices on the hot raw tables.** `raw.retrosheet_event` (16.5M rows) is indexed only
   on `game_id` — nothing on `pit_id` / `bat_id`. `raw.statcast_pitch` (13.5M rows) — nothing on
   `pitcher` / `batter`. The slow point-in-time queries in (4) seq-scan the full table on HDD.
7. **Hardware:** 40 cores, 125 GB RAM, Postgres 16.15, `shared_buffers` 32 GB, `effective_cache_size`
   96 GB, parallel workers ≤ 40. **All six disks are rotational SAS HDDs** (no SSD); PG data on
   `/mnt/storage/postgres-data`. Postgres is *not* CPU- or RAM-starved. The bottleneck is disk
   random I/O + rebuild-everything design + the slow queries in (4).
8. **Machine contention:** ~40 other cron jobs (sysmon) fire every 1–5 min plus the every-5-min
   `mlb_api_update`. Load average 13.5 during investigation.

## Goals

- The daily job completes reliably again, and a mid-run failure is **observable** (which step,
  why) and **resumable** (re-run picks up, doesn't restart from zero).
- Daily `mlb predict` completes in **well under 30 min**, and a mid-run failure loses minutes, not
  the whole feature build (checkpointed progress).
- A single `conform` or `predict` invocation is cheap enough to iterate on during development.
- Full integration test suite runs in **≤ 5 minutes** (currently ~52 min on CI).
- Every change is measured before/after (`pg_stat_statements`, `EXPLAIN (ANALYZE, BUFFERS)`,
  wall-clock) — no "should be faster" claims without a number.

## Phase 0 — get the daily job green again (do first, this week)

Reliability before speed. The pipeline that never finishes is worse than the slow one.

### 0.1 Split `update` / `conform` / `predict` into separately-locked, separately-logged steps

`scripts/mlb_daily_update.sh` runs all three under one `flock` + `set -e`, so a hiccup in `update`
(exactly what's happening) silently skips `conform` and `predict` with no distinct signal. Give
each its own lock, its own log section with start/end timestamps and exit code, and let `predict`
run off the freshest `core.game` even if that morning's `update` had a partial failure.

### 0.2 Fix the `mlb_api` self-lock conflict

The daily `mlb update` iterates every connector including `mlb_api`, but the every-5-min
`mlb_api_update` cron usually holds the `mlb_api` ingestion lock at 06:00 — so the daily run's
`mlb_api` step fails every time. Options: have the daily `update` skip `mlb_api` (the 5-min cron
already keeps it fresh), or pause the 5-min cron for the daily window. Decide and implement.

### 0.3 Make `mlb update` resilient to one connector stalling

Kalshi `429` retry stalls and any single hung connector shouldn't be able to wedge the whole run.
Per-connector timeout + "log, mark failed, continue" (the script already does `continue` on
failure for some — make it uniform and time-bounded).

### 0.4 `mlb doctor` check: predictions stale — ALREADY EXISTS

Verified 2026-08-28: `model.health_check()` already calls
`check_recent_run(SOURCE, DAILY_FRESHNESS_THRESHOLD_MINUTES=28h, mode="bootstrap")`, which
currently reports `False | last run running, not success` against production. No new check needed.
Real gap found instead: killed (SIGKILL) `predict` runs leave `meta.ingestion_run` rows stuck in
`running` (Aug 25/26 rows still `running`) because `track_run` only reconciles on a caught
exception. Follow-up: reconcile stale `running` rows to `failed` on the next run's startup.

### 0.5 Supervised backfill

Once 0.1–0.3 land, one owner-authorized `mlb conform && mlb predict` run against production
(`DATABASE_URL=postgresql:///mlb`, stated explicitly) to catch up the 8 missing days, watched to
"finished".

## Non-goals (this spec)

- Migrating production to the Postgres 17 instance on port 5434 (real upside — PG17 streaming I/O
  for seq scans helps HDDs — but it's its own migration project; tracked as a follow-up issue,
  not done here).
- Rewriting the sabermetric logic of any enrichment module (that's the separate metrics-layer
  work). This spec only changes *how often* and *in what transaction shape* they run.
- Buying SSDs or changing hosting ($0/month constraint).

## Phase 1 — quick wins, no restructure (target: predict ~1h → <30 min, tests → ~10 min)

Each item ships as its own commit with a measured before/after in the message.

### 1.1 Make `gold.leverage_index` / `gold.win_expectancy` incremental + crash-safe

Today: "build once if empty, else full no-op" — so a normal daily run doesn't pay for it, but a
single clear of the table triggers a 4.5-hour inline rebuild, and the current season's new games
are **never** folded in after the first build. Change `compute()` to:
- Store a per-season fingerprint (max `game_date` + row count of the source).
- Recompute **only** seasons whose fingerprint changed (in practice: the current season each day,
  plus any season touched by a backfill).
- Stay a true no-op (one `SELECT` of the fingerprint) when nothing changed.
- Never leave the table empty on a mid-rebuild failure (build into staging, swap at the end).

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

1. **Phase 0 first** — small PRs, each independently revertable. After 0.1–0.4, re-enable the
   daily cron and watch a real run reach "finished daily update". Then 0.5 (supervised backfill).
2. Phase 1 lands as small PRs, each with a measured before/after.
3. Phase 2 and 3 follow as separate specs/plans if this one gets too large to execute as a unit.

## Open questions for the owner

1. OK to run `mlb_test`'s cluster with `fsync=off` / on tmpfs? (Safe — disposable DB — but worth a
   yes.)
2. PgBouncer: acceptable to add as a system service, or prefer application-side pooling
   (`psycopg_pool`) to keep the deploy simpler?
3. Priority order if Phase 1 is still too slow to iterate: push straight to Phase 3 (incremental)
   for `conform`, or finish Phase 2 (reliability) first?
