# Session handoff — 2026-09-27

Branch: `feat/raw-source-tieout`. Everything below is committed (`HEAD` is
`8e69164`); nothing is sitting uncommitted except an untracked `.idea/`
(IDE config, not ours, left alone). Read this instead of re-deriving context.

## 1. `raw-source-tieout` OpenSpec change — in progress, on track

Read `openspec/changes/raw-source-tieout/tasks.md` for the live checklist.

**Done (tasks 1.1–3.1, all committed):** the full read-only Retrosheet
tie-out gate exists (`mlb_baseball/tieout.py`, `mlb_baseball/tieout_run.py`,
`scripts/verify_retrosheet_tie_out.py`), covering season/game/player-game
comparisons across every redundant Retrosheet source, a `core.play`/`core.game`
completeness check, a pinned production column-contract check
(`mlb_baseball/tieout_schema_contract.py`, task 2.6), and — just finished this
session — pinned column-contract tests for the event/game/CSV tables against
the connector's own real output in the disposable test database
(`mlb_baseball/tieout_connector_columns.py`, `tests/integration/
test_tieout_connector_columns.py`, task 3.1). All of it has real-Postgres
integration tests, not mocks.

**A real finding from task 3.1, already documented, no action needed:**
production's `raw.retrosheet_event` has 3 legacy columns (`run1_auto_fl`,
`run2_auto_fl`, `run3_auto_fl`) that a fresh load can no longer produce, left
over from before ADR-060 narrowed `CWEVENT_EXTENDED_FIELDS` from `0-66` to
`0-63`. Re-tested ADR-060's claimed `cwevent` failure directly against the
currently installed Chadwick 0.10.0 binary and a modern (2024) fixture:
`-x 0-66` succeeds and does **not** reproduce the failure. This is not treated
as evidence the ADR-060 fix was wrong (the original failure may be specific to
the older/deduced event file that triggered it, not retested here) — flagged
in `audit.md` finding G10 and a dated comment in `chadwick_tools.py` so it
isn't rediscovered as a mystery. Also resolved audit finding G9 in the same
change (the pinned column contract is the *union* of every era's columns,
since `load.py` only ever adds columns via `ALTER TABLE`, never drops one —
no per-era allowed set needed).

**Next task is 3.2** (close the remaining audit gaps — at minimum an
integration test that loads a small real event fixture and checks known
counts; verify each gap in `audit.md` is marked closed or has an issue
number), then 4.x (real runs against production `mlb` for 2015–2025 and
history, recorded in `results-2015-2025.md`/`results-history.md`).

**PRs:** #261 (this change's planning) and #262 (play-engine event-code
mapping) are both merged. Nothing outstanding there.

## 2. Server performance investigation — root cause found, partially fixed

The disposable-test-database setup was taking minutes instead of seconds.
Fully diagnosed with real measurements, not guesses:

- This Postgres server (v16, at `/mnt/storage/postgres-data`) is **shared**
  across several unrelated databases/projects (`mlb` 62GB, `govdata` 35GB,
  `promscale`, etc.) and sits on a 5-disk spinning RAID5 array — confirmed via
  `/proc/mdstat` and `/sys/block/*/queue/rotational`. No SSD/NVMe in the mix.
- `shared_buffers` is set very large (~40GB) cluster-wide.
- **The actual mechanism, proven live:** `DROP DATABASE` forces Postgres to
  run a full checkpoint before it can finish. Measured directly: creating an
  *empty* database took 2.5s; dropping that same empty database took **5
  minutes 53 seconds**, because the forced checkpoint has to flush everything
  dirty in `shared_buffers` cluster-wide, and that was competing with two
  real concurrent jobs at the time (see below).
- **Reconfirmed again this session:** while running task 3.1's tests, a real
  `mlb` production cron `INSERT` and an unrelated `opendiscourse` pytest run
  were both active at once, and one test run hit a genuine (if rare)
  `psycopg.errors.ObjectInUse` on the disposable database's template during
  setup. Retried once and it passed cleanly (8/8) — same root cause as below,
  not a new bug, not code-related (the same tests had already passed 4/4 in
  isolation moments earlier).
- **Why it happened originally:** your own crontab runs `mlb_daily_update.sh`
  (update → conform → predict) at 6am — confirmed via `pg_stat_activity`, an
  `mlb conform` process was actively inserting into `core.play` right when
  this was measured. At the same time, an unrelated `research-db
  acs-bulk-load` job (a *different* project, `opendiscourse`, 6 workers) was
  also running — it isn't in any crontab I can see, so it was started some
  other way. Both were fighting the same disks.
- **Fixed already (committed, `2f4c430`):** `tests/conftest.py` was setting
  `synchronous_commit = off` *after* running migrations instead of before, so
  every migration commit (~100+) paid full WAL-flush latency for nothing.
  Reordered.
- **Fixed already (partial help only):** set up a tmpfs (RAM-backed)
  Postgres tablespace, `mlb_test_tmpfs`, at `/mnt/pg_test_tmpfs/data`, with a
  persistent `/etc/fstab` entry and a `systemd-tmpfiles.d` rule
  (`/etc/tmpfiles.d/pg_test_tmpfs.conf`) so it survives reboots. `conftest.py`
  now moves the test database onto it automatically if it exists, otherwise
  falls back to the default tablespace (never a hard requirement). **Measured
  result under real contention: only went from ~21 minutes to ~20 minutes** —
  it speeds up building/dropping the test database's own ~300+ relation
  files, but it does **not** avoid the forced-checkpoint wait itself, because
  that checkpoint flushes dirty pages from *all* concurrent activity, not
  just our database's own files.
- **Conclusion, agreed with the owner:** the real fix is preventing heavy
  jobs from overlapping in the first place, not tuning the test database
  further. See section 3.

## 3. New, agreed next feature: an MLB-scoped job queue/coordinator

**Decision made last session (owner's explicit direction):** build a small
job-queue/coordinator system, but scoped to *this* project only — living
**inside the `mlb` Postgres database** and shipped as part of the `mlb`
repo, not a separate cross-project `infra` tool. The owner will build the
equivalent for `opendiscourse` separately themselves (it doesn't currently
have any scheduled jobs). Do not build a shared cross-repo `ops` database —
that idea was proposed and explicitly rejected in favor of this.

**What it needs to do**, per the owner's own words:
- Space out / coordinate `mlb`'s own cron jobs (`mlb_api_update.sh` every 5
  min, `mlb_daily_update.sh` at 6am, plus any future heavy job) so they don't
  overlap and don't each fight the disk at once.
- Live in a table (or a few tables) inside the `mlb` database — a real
  job-queue pattern (Postgres's `SELECT ... FOR UPDATE SKIP LOCKED` is the
  standard, well-established way to do this; no new external dependency is
  obviously required for something this size — see
  `AGENTS.md` "Established solutions first" before reaching for a library).
- Record successes, failures, and support retries — i.e., real observability
  of what ran, when, how long it took, and whether it failed — not just a
  bare lock.
- pg_cron is already installed on this server (`shared_preload_libraries`
  includes it) but is unused (`cron.job` is empty). It's a real option worth
  weighing for *scheduling* pure-SQL work, but note: it does not run
  arbitrary shell/Python jobs on its own, and it does not by itself prevent
  two jobs from colliding — a lock/queue is still needed on top either way.
  Don't assume switching everything to pg_cron alone solves this.

**Still not started.** This is new scope, not yet proposed as an OpenSpec
change. Per this project's workflow (`openspec/project.md`), the next step
should be `/opsx:propose` for this (something like
`mlb-job-coordinator` or similar name) before writing code, covering: the
schema (queue/run-log tables, migration), which existing cron entries adopt
it and how, retry semantics, and how it's tested.

## 4. Where to pick up next

1. Read this file, then `openspec/changes/raw-source-tieout/tasks.md`.
2. Either continue `raw-source-tieout` task 3.2, or propose the new
   job-coordinator change (`/opsx:propose`) per the owner's direction in
   section 3 above — ask the owner which they want first if unclear.
3. Nothing is uncommitted; nothing is mid-edit; no background jobs need
   watching.
