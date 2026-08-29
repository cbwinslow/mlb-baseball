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

## Full `pg_stat_statements` sweep by command — 2026-08-29 (postgres-mcp + hypopg)

Every project query on production `mlb`, ranked and attributed to the command that runs it.
`×N` = calls in a 13-day window (≈ daily runs + manual iteration).

| command | query | mean | calls | fixable by |
| --- | --- | ---: | ---: | --- |
| `doctor` + `predict` | `starter_probable_expected.sql` (join-coverage denominator) | **290 s** | 84 | **index (0092)** — done in this branch |
| `predict` | `batted_ball_rates` entering-game (BAT-*) | 213 s | 3 | incremental (full-history GROUP BY over `raw.retrosheet_event`) |
| `predict` | `pitch_discipline` entering-game (PIT-*) | 178 s | 3 | incremental |
| `predict` (or `leverage` rebuild) | `leverage_index` per-season staging | 128 s | 228 | `_season` index (0092) + incremental (spec 1.1) |
| `predict` | bullpen "regular_games" reconstruction | 110 s | 3 | incremental |
| `predict` | base `game_feature` family build | 109 s | 3 | incremental |
| `predict` | starter career experience (PLN-04) | 91 s | 3 | incremental |
| `predict` | comprehensive baserunning (BsR/wSB/XBT) | 76 s | 3 | incremental |
| `predict` | team OBP/SLG/ISO/BB%/K% rolling (OFF-01/02/03) | 68 s | 3 | incremental |
| `doctor` | `starter_strikeouts_reconcile.sql` (vs bref_pitching) | 42 s | 84 | scope to recent seasons for the *daily* check |
| `audit`/`conform` | `core.play` DISTINCT-ON / dedup checks | 28 s | ~85 | scope / incremental |
| `doctor` | `starter_outs_reconcile.sql` + relief/starter outs reconcile | 25 s | 160 | scope to recent seasons |
| `conform` | `TRUNCATE core.play, core.pitch, … gold.game_feature` | 10–16 s | 62 | incremental (truncate-and-rebuild-all-129-seasons) |
| — | `SELECT pg_database_size()` | 5 ms | **1.5 M** | external monitoring poller, **not this project** |

**The shape of it:** `predict`'s ~47 min is ~30 enrichment modules that each do a full-history
aggregate over `raw.retrosheet_event` (16.5 M rows) on every run. **Indexes (0090, 0092) fix the
point queries; they cannot speed up a full-table `GROUP BY`.** The only lever for the `×3`
enrichment queries is **incrementality** — only recompute seasons whose events changed (Phase 3 /
issue #70 SQLMesh). 1950's baserunning rates do not change; recomputing them nightly is the cost.
`doctor`'s reconcile checks (`×84`/`×160`) similarly reconcile all history every run — a daily
health check only needs the last 1–2 seasons; keep the full-history reconcile as a
weekly/pre-release audit.

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

### 0.1 Split `update` / `conform` / `predict` into separately-tracked steps — DONE (PR #85)

`scripts/mlb_daily_update.sh` ran all three under one `flock` + `set -e`, so a hiccup in `update`
(exactly what was happening) silently skipped `conform` and `predict`. Implemented: each step is a
`run_step` unit with its own start/end timestamp and exit code; a failure in one still attempts the
next; the script's overall exit code is non-zero if any failed. `set -e` removed. Lock/log paths
are overridable (`MLB_DAILY_LOCK_FILE` / `MLB_DAILY_LOG_FILE`) so tests and a second checkout don't
contend. Tests: `tests/unit/test_daily_update_script.py`.

### 0.2 Fix the `mlb_api` self-lock conflict — DONE (PR #85)

The every-5-min `mlb_api_update` cron holds the `mlb_api` ingestion lock at 06:00, so the daily
run's `mlb_api` step failed every day on "another ingestion run is already active". Implemented:
`mlb update` / `mlb bootstrap` gained a repeatable `--skip CONNECTOR` (unknown name → exit 2, all
connectors skipped → clean no-op), and the daily script runs `mlb update --skip mlb_api`. Docs
(`ARCHITECTURE.md` scheduling, `ROADMAP.md` 8c) updated in the same PR. Tests:
`test_cli_dispatch.py::test_update_skip_*`.

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

Once 0.1–0.3 land (owner has chosen to hold this until Phase 1's speed wins land first), the
sequence:
1. `mlb audit` against `mlb_test` — resolve every `FAIL`, document every `WARN`, get explicit
   owner approval to proceed.
2. One `mlb conform && mlb predict` run against production (`DATABASE_URL=postgresql:///mlb`,
   stated explicitly in the command) to catch up the missing days, watched to "finished".
3. `mlb audit` against production again; retain its output with the run record in
   `plans/PROGRESS.md`.

## Non-goals (this spec)

- Migrating production to the Postgres 17 instance on port 5434 (real upside — PG17 streaming I/O
  for seq scans helps HDDs — but it's its own migration project; tracked as a follow-up issue,
  not done here).
- Rewriting the sabermetric logic of any enrichment module (that's the separate metrics-layer
  work). This spec only changes *how often* and *in what transaction shape* they run.
- Buying SSDs or changing hosting ($0/month constraint).

## Phase 1 — quick wins, no restructure (target: predict ~1h → <30 min, tests → ~10 min)

Each item ships as its own commit with a measured before/after in the message.

### 1.0 Cluster-wide Postgres config — DONE (owner ran `scripts/pg_tune.sql`)

The PG16 cluster (port 5432) is shared by `mlb`, `govdata` (62 GB), `promscale`, `langfuse` and
others — 40 cores, 125 GB RAM. `work_mem` was **25 MB**, so the big enrichment sorts/hashes spilled
to disk (fatal on HDD). Reload-only changes (no restart; reverse any with `ALTER SYSTEM RESET
<name>`), in `scripts/pg_tune.sql`:

| Setting | From | To | Why |
|---|---|---|---|
| `work_mem` | 25 MB | 128 MB | keep normal sorts/hashes in RAM; batch jobs raise it to 1 GB per-session (1.2) |
| `hash_mem_multiplier` | 2 | 3 | hash joins/aggregates (the enrichment queries) get `work_mem × 3` |
| `maintenance_work_mem` | 2 GB | 4 GB | faster index builds / `VACUUM` |
| `max_parallel_maintenance_workers` | 2 | 6 | parallel index builds on the 16 M-row raw tables (1.3) |
| `random_page_cost` | 4 | 2 | 32 GB `shared_buffers` + 96 GB OS cache — index scans mostly hit cache. The one change with plan-shift risk across the other DBs; watch, `RESET` if a regression shows. |
| `checkpoint_timeout` | 15 min | 30 min | spread checkpoint I/O during bulk loads (`max_wal_size` already 32 GB) |
| `effective_io_concurrency` | 16 | 32 | 6-disk array, not a single spindle |
| `parallel_setup_cost` | 1000 | 200 | planner was choosing serial plans for the big aggregations (see below) |
| `parallel_tuple_cost` | 0.1 | 0.05 | ″ |

**Measured 2026-08-28** on COM-01's core aggregation (`raw.statcast_pitch` 13.5 M rows joined to
all regular games, GROUP BY game+pitcher, then a rolling window) — historically ~1,070 s as part
of the full statement:

| Config | Wall time |
|---|---|
| baseline (`work_mem` 25 MB, serial) | ~18 min (spilled the 434 MB hash aggregate to disk in dozens of batches) |
| `work_mem` 1 GB, serial | **60 s** (hash agg in 1 in-memory batch; ~36 s of that is the cold seq scan) |
| `work_mem` 1 GB + 7-worker parallel seq scan + warm cache | **~5 s** |

Restart-required round: `scripts/pg_tune_restart.sql` — restart-required `shared_buffers` 32 GB →
40 GB and `wal_buffers` 16 MB → 64 MB, plus reload-only `effective_cache_size` → 100 GB and
`bgwriter_lru_maxpages` 100 → 1000. `pg_prewarm` (`CREATE EXTENSION` + a one-time
`pg_prewarm('raw.retrosheet_event')` / `raw.statcast_pitch` / `gold.game_feature`) is a manual
operational step in the runbook, not a config or schema change — `shared_preload_libraries` is
left untouched (an `ALTER SYSTEM SET` there replaces the whole list and a bad entry stops the
cluster). Gain is an **unvalidated ~10–20% estimate**: the box already holds ~104 GB of file data
in the OS page cache, so the hot tables are rarely read cold — the real nightly cost is CPU
(window aggregates) and the ~30 M-row rebuild write, which the structural work (Phase 3) targets.
Optional follow-on in the same script: huge pages (`vm.nr_hugepages`, count derived from
`shared_memory_size_in_huge_pages` after the 40 GB `shared_buffers` is live).

### 1.1 Make `gold.leverage_index` / `gold.win_expectancy` incremental + crash-safe

Today: "build once if empty, else full no-op" — so a normal daily run doesn't pay for it, but a
single clear of the table triggers a 4.5-hour inline rebuild, and the current season's new games
are **never** folded in after the first build. Change `compute()` to:
- Store a per-season fingerprint (max `game_date` + row count of the source).
- Recompute **only** seasons whose fingerprint changed (in practice: the current season each day,
  plus any season touched by a backfill).
- Stay a true no-op (one `SELECT` of the fingerprint) when nothing changed.
- Never leave the table empty on a mid-rebuild failure (build into staging, swap at the end).

### 1.2 Per-session durability/memory pragmas for the rebuild — DONE (this PR)

`db.apply_batch_session_settings(conn)` — session-level `SET` (not `SET LOCAL`: these jobs commit
between stages), called once right after opening the connection in `conform.run()`,
`model.run()`, and `model.run_features()` only (never the 5-minute ingestion cron or the test
suite — they run concurrently and a work_mem bump there could OOM):
- `synchronous_commit = off` — rebuild from a reproducible source; a crash just re-runs.
- `work_mem = 1GB` — the point-in-time enrichment sorts/hashes spilled to disk at the 25 MB
  cluster default (fatal on HDD). Safe at 1 GB because the `exclusive` workflow lock means one
  such job at a time.
- `maintenance_work_mem = 4GB` — index maintenance during the rebuild.

Mirrors the **already-proven** test-DB pattern (`tests/conftest.py::_speed_up_test_database`,
measured bulk `TRUNCATE` 79–84 s → ~20 s). Tests:
`tests/integration/test_batch_session_settings.py`.

### 1.3 Targeted indices on raw tables — validated with `hypopg` first

Install `hypopg` (hypothetical indexes — test benefit without paying the multi-hour build on HDD).
For each 14–18 min enrichment query: `EXPLAIN` with hypothetical indexes on candidate keys
(`raw.retrosheet_event(pit_id)`, `(bat_id)`, `(pit_id, game_id)`; `raw.statcast_pitch(pitcher)`,
`(batter)`, `(pitcher, game_date)`). Build **only** the ones that change the plan and the measured
time. Document each in a migration with the before/after `EXPLAIN`. Reject any that don't earn
their keep (every index slows the COPY ingestion path).

**Migration 0090 (DONE):** `raw.retrosheet_event(pit_id)` / `(bat_id)`,
`raw.statcast_pitch(pitcher)` / `(batter)` — applied to production; the Phase 1 index work
that got `mlb predict` from 2h+ to ~47 min alongside 1.0/1.2.

**Migration 0092 (this change):** `hypopg` installed on production `mlb` 2026-08-29;
`pg_stat_statements` (13-day window) re-ranked. Two new hot queries, not covered by 0090:

| query | source | calls | mean | fix |
| --- | --- | ---: | ---: | --- |
| starter probable "expected" count | `starter_probable_expected.sql` (starter.py health check, runs in `mlb doctor` **and** every `mlb predict`) | 84 | **290 s** | `EXPLAIN`: its `EXISTS` is a Nested Loop that seq-scans `raw.mlb_schedule` (236 k) + `raw.mlb_playbyplay` (170 k) per candidate starter. → `raw.mlb_playbyplay(pitcher_id, game_pk)` + `raw.mlb_schedule(game_id)`. Both tables <150 MB. |
| `leverage_index` per-season staging | `leverage_index_matrix_build` | 228 | 128 s | `WHERE re._season::integer = $1` seq-scans `raw.retrosheet_event` (16.5 M / 11 GB); no `_season` index. → expression index `((_season)::integer)`, matching `retrosheet_event_outs_ct_int_idx`. Real fix is 1.1 (incremental); this index also unblocks it. |

Restricted (read-only) MCP access blocks `EXPLAIN (ANALYZE)`, so the wall-clock lands in
`pg_stat_statements` after apply. But `hypopg` gives a quantified plan-cost before/after:

| query | current plan | with 0092 index (hypopg) |
| --- | --- | --- |
| `starter_probable_expected` EXISTS (one iteration) | Nested Loop, seq scan `mlb_playbyplay` + seq scan `mlb_schedule`, **cost 31,400** | Index Only Scan `pbp(pitcher_id)` → Index Scan `ms(game_id)`, **cost 338** (~90×). Runs ~80–160×/call. |
| `leverage_index` per-season scan | Seq Scan `retrosheet_event`, 16.5 M rows, **cost 1,399,165** | Bitmap Index Scan on `((_season)::integer)`, ~82 k rows, **cost 143,568** (~10×) |

**The enrichment queries an index *cannot* fix.** `EXPLAIN` of the `×3` enrichment modules
(`team_batted_ball_retrosheet_update.sql` 213 s, `team_pitch_discipline_retrosheet_update.sql`
178 s, starter career experience 91 s, comprehensive baserunning 76 s, team-rate rolling 68 s):

```text
WindowAgg  (cost 3,046,888)
  → Gather Merge
    → Sort  (cost 1,601,697)          -- spills to HDD
      → Seq Scan on retrosheet_event  (cost 1,346,083)   -- all 16.5 M rows, NO WHERE clause
```

Each has `FROM raw.retrosheet_event re` with **no filter at all** — a `ROWS BETWEEN UNBOUNDED
PRECEDING AND 1 PRECEDING` window over every event of every season, every run. An index can't
help a window that needs every row. The only lever is a `WHERE re._season >= <current-lookback>`
(Phase 3 / issue #70): 1950's rates don't change, so recomputing them is pure waste. The
`((_season)::integer)` index in 0092 is the prerequisite for that filter being fast.

**Also open** — the two `raw.retrosheet_event` full-history reconcile checks in
`starter.py::health_check` (`starter_strikeouts_reconcile.sql` 42 s × 84,
`starter_outs_reconcile.sql`): they GROUP BY every player-season over 16 M rows every run. A
daily health check only needs the last 1–2 seasons; keep the full reconcile as a
weekly/pre-release audit.

### 1.4 CI Postgres `fsync=off` — DONE

The CI `integration` job's Postgres is a container destroyed after the run — crash-safety buys
nothing. `.github/workflows/ci.yml`'s existing service-config step now also sets
`fsync=off` / `synchronous_commit=off` / `full_page_writes=off` / `wal_level=minimal` /
`max_wal_senders=0` cluster-wide before the restart. Cluster-wide is only safe *there* (a
dedicated container); locally `mlb` and `mlb_test` share a cluster, so `tests/conftest.py` keeps
its per-database relaxations (issue #2). Local `mlb_test` on tmpfs is a separate, optional
contributor-machine tweak (README "Testing").

### 1.5 `pytest-xdist` with schema/database-per-worker

Add `pytest-xdist`; each worker clones its own database from the pre-migrated template (the
conftest already builds one via `postgresql_noproc`). Target: 563 integration tests across 8–12
workers. Fixes the wall-clock; the fixture-ordering bugs (#78, #58, #56, #67) must be fixed in the
same effort or xdist will surface them as flakes.

### 1.6 Diagnostic extensions

`CREATE EXTENSION` on `mlb` (all low-risk, reversible): `hypopg`, `pg_prewarm` (warm
`shared_buffers` after restart so first queries aren't cold HDD reads), `pg_buffercache`,
`pgstattuple`, `pg_stat_kcache`. (No new stale-prediction check — 0.4 covers that at the existing
28 h threshold.)

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

### DuckDB spike — the "compute layer" question

The owner asked whether to ingest raw into Postgres and run the slow calculations in a separate
engine. DuckDB is the low-commitment way to test that: embedded (no server), free, columnar +
vectorized, can read Postgres directly (`postgres` extension) and read/write Parquet.

**Spike (do after Phase 1.0–1.3 are measured, not before):** take the single slowest enrichment
query — COM-01 "strike zone command" (1,070 s in Postgres) — and reimplement it in DuckDB reading
from `raw.retrosheet_event` / `raw.statcast_pitch` (via the postgres scanner, or a one-off Parquet
extract). Measure wall-clock and correctness (row-for-row identical output). Decision rule:

- Phase 1 alone gets the query under ~2 min → **stop, Postgres is fine.**
- Phase 1 + SQLMesh incremental (Phase 3) gets the *daily* run acceptable → **stop.**
- Still too slow, and DuckDB is >5× faster on the spike → adopt DuckDB as the enrichment compute
  layer (raw stays in Postgres; heavy transforms run in DuckDB; results written back to `gold`).
- ClickHouse stays deferred per `docs/CLICKHOUSE_DECISION.md` — its place is the public serving
  path (many concurrent readers), a Phase 5 concern, not the nightly batch.

**Postgres 17 (port 5434):** real upside for this HDD-bound workload (PG17 streaming I/O for
sequential scans, better parallel-scan scheduling, faster `VACUUM`). But it's a 55 GB data
migration + revalidating every connector, migration, and test against a new major version.
Separate follow-up issue; revisit after Phase 1–2 land and we know how much headroom remains.

## Testing strategy

Canonical commands (same as CI's four jobs in `.github/workflows/ci.yml`, Python 3.11, `uv.lock`
frozen): `uv sync --frozen --extra dev`, then `uv run ruff check . && uv run sqlfluff lint
mlb_baseball/sql/ && uv run mypy` (lint), `uv run pytest tests/unit -q` (unit), `uv run pytest
tests/integration -q` against a real `mlb_test` Postgres (integration). Debug a Phase 0 check by
running the one script/command it wraps directly with `-x -q` and reading `logs/mlb_daily_update.log`.

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

1. **Phase 0 first** — small PRs, each independently reversible. After 0.1–0.4, re-enable the
   daily cron and watch a real run reach "finished daily update". Then 0.5 (supervised backfill).
2. Phase 1 lands as small PRs, each with a measured before/after.
3. Phase 2 and 3 follow as separate specs/plans if this one gets too large to execute as a unit.

## Open questions for the owner

1. ~~OK to run the CI Postgres container with `fsync=off`?~~ **Resolved** — done in §1.4
   (dedicated disposable container). Still open, lower priority: running the *local* `mlb_test`
   on tmpfs on a contributor machine, where it shares a cluster with `mlb` (optional tweak only).
2. PgBouncer: acceptable to add as a system service, or prefer application-side pooling
   (`psycopg_pool`) to keep the deploy simpler?
3. Priority order if Phase 1 is still too slow to iterate: push straight to Phase 3 (incremental)
   for `conform`, or finish Phase 2 (reliability) first?
