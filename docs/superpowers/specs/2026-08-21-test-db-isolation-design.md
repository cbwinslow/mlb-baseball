# Test database isolation: adopt pytest-postgresql, retire the single shared `mlb_test` lock

**Status:** Design spec, not yet an implementation plan. Written via `superpowers:brainstorming`
on 2026-08-21 with the project owner.

## Objective

Today, every `pytest` invocation — local, in any of up to 8 concurrent agent worktrees, or in
CI — reserves the *same* single `mlb_test` database via one session-scoped, non-blocking advisory
lock (`hashtext('mlb-test-suite')`, `tests/conftest.py:120-184`). Only one test session can run
system-wide at a time; a second one fails immediately with "already reserved by pid X." If a
session dies mid-run without releasing the lock (observed live this session: pid 359194 sat `idle
in transaction` holding it for 15+ minutes), every other agent is blocked until a human manually
runs `pg_terminate_backend`.

This spec replaces the single shared database + global lock with **one isolated, disposable
database per test run**, built by cloning a pre-migrated template — the same pattern Django's and
Rails' built-in parallel test runners use, implemented for pytest by the `pytest-postgresql`
library. The goal is: any number of agents can run the full suite at the same time, with no
lock, no manual recovery, and (as a side effect) without re-running every migration from scratch
on every single invocation.

## Current state (verified against source, not assumed)

- `tests/conftest.py:120-184` — one `session`-scoped, `autouse=True` fixture (`_test_database`):
  asserts `TEST_DATABASE_URL` names a disposable database, points `DATABASE_URL` at it, takes the
  global advisory lock (fails fast if held), runs `migrate.run()`, then applies test-only
  durability relaxations, then yields.
- `_speed_up_test_database` (`tests/conftest.py:69-117`): `ALTER DATABASE ... SET
  synchronous_commit = off` plus `ALTER TABLE ... SET UNLOGGED` on ~316 `core.play`/`core.pitch`
  season partitions — a measured fix (bulk `TRUNCATE` 79-84s → ~20s), reapplied unconditionally
  on every session start.
- `db_conn` fixture: plain non-autocommit `psycopg.connect(TEST_DATABASE_URL)` per test — matches
  `mlb_baseball.db.get_connection()` exactly, because `test_ingest_tracking.py`'s regression test
  for `track_run`'s rollback behavior depends on real (not wrapped/rolled-back) commit semantics.
- `drop_tables_after` fixture: opt-in per-test cleanup through the *same* connection a test used.
- `_assert_test_database_url`: hard-fails the whole suite if the target database name doesn't
  contain "test" — this is the one guarantee that a test run can never touch production `mlb`.
  **This spec does not weaken or remove this guarantee anywhere it applies today; it extends the
  same principle to every new database name this design introduces (see "Safety" below).**
- 931 total tests: 368 unit (no DB), 563 integration (real Postgres).
- CI (`.github/workflows/ci.yml`): one linear job — lint, sqlfluff, mypy, build Chadwick CLI
  tools, then the full suite (`pytest -q --cov=...`) — against a Postgres 16 **service container**
  GitHub spins up fresh per run. CI already gets an isolated, empty-then-migrated server per run;
  it is not part of the contention problem this spec solves, but the same conftest.py code path
  should serve it too (see "CI" below) rather than branching local vs. CI logic.
- No existing use of `pytest-xdist` or any DB parallelization tooling anywhere in the repo.

## Why `pytest-postgresql`, not a hand-rolled version

Verified against the library's current README/CHANGES (v8.1.0, Python ≥3.10, Postgres ≥14 — 16 is
fine):

- `postgresql_noproc` connects to an **already-running** server (host/port/user, not a managed
  `initdb` process) — matches this project's always-on local Postgres exactly.
- The `postgresql` client fixture builds a template database once, then clones it per test/session
  via `CREATE DATABASE ... TEMPLATE` — Postgres's own file-copy mechanism, not a logical replay of
  migrations (see [Postgres docs, §22.3](https://www.postgresql.org/docs/current/manage-ag-templatedbs.html)).
- `load` accepts a plain Python callable (in addition to raw `.sql` files) — `migrate.run()` plugs
  in directly as "how to build the template," no Django/Alembic-specific shim needed.
- Returns real `psycopg` v3 connections/DSNs (native since v4, mandatory since v5) — no bridging
  from psycopg2.

This keeps `db_conn`, `drop_tables_after`, and the overall fixture shape essentially unchanged; it
replaces the hand-written lock-and-shared-database machinery in `_test_database`, not the rest of
the file.

**What it does *not* solve by itself:** `pytest-postgresql`'s parallelism story
(`postgresql_noproc` + `pytest-xdist`) is designed for multiple *workers inside one `pytest`
invocation*. This project's actual concurrency is multiple *separate* `pytest` invocations (one
per agent/worktree) at the same time — a different axis the library doesn't address out of the
box (confirmed via GH issue #470/#501, which was specifically about xdist workers colliding on
generated names). This spec's design below adds the missing piece: explicit, high-entropy unique
naming per invocation, not reliance on xdist's worker-id scheme.

## Design

### 1. Template database

- One template database, e.g. `mlb_test_template`, built by calling `migrate.run()` against it
  (via `load`), then applying the existing `_speed_up_test_database` tweaks **once**, against the
  template, instead of once per session as today.
- **To verify during implementation, not assumed:** whether `ALTER TABLE ... SET UNLOGGED`
  (a catalog property, `pg_class.relpersistence`) survives being cloned via `CREATE DATABASE ...
  TEMPLATE` the way ordinary table data does. If it does, this is a straightforward win over
  today's per-session reapplication. If it doesn't, fall back to reapplying it per clone (still
  cheaper than today, since `_drop_bulk_indexes`-style whole-suite reruns go away, but worth
  confirming empirically with a throwaway `psql` test before relying on it in the design).
- `synchronous_commit = off`: apply at the **session/connection level** (`SET
  synchronous_commit = off`, not `ALTER DATABASE`) inside the loader/fixture, per clone — this
  sidesteps any ambiguity about whether an `ALTER DATABASE`-level setting is copied to a new
  database with a new OID (it likely is not), and costs effectively nothing to reapply.
- Template staleness: rebuild the template when the migrations directory's content changes since
  it was last built (e.g. a stored hash/mtime check against `migrations/`), not on every run.
  Rebuilding the template is a **shared, mutually-exclusive** operation across concurrent
  invocations — this is the one place a lock is still needed (see "Safety" below), scoped narrowly
  to "is the template stale, and if so, rebuild it," not to the whole test run.

### 2. Per-run database naming and cleanup

- Each `pytest` invocation clones the template into its own uniquely-named database — e.g.
  `mlb_test_<12 hex chars from secrets.token_hex>` — rather than relying on any library default
  or xdist worker-id scheme, since the real requirement (uniqueness across *separate process
  invocations*, not workers within one process) isn't what those defaults guarantee.
- Drop the clone in a session-scoped teardown (`finally`/fixture teardown), same as today's
  pattern, just against the per-run database instead of truncating a shared one.
- Orphaned clones (a crashed session that never reached teardown) are not a contention problem
  anymore — they don't block anyone else — but they do consume disk. Sweep them with a small
  maintenance check: drop any `mlb_test_<hex>` database older than some threshold (e.g. a few
  hours) whose name doesn't match a currently-connected session in `pg_stat_activity`. This can be
  a `mlb doctor` health check (per this project's existing convention of giving every module with
  a way to be "unhealthy" a check) or a standalone script — decide during implementation.

### 3. Safety — preserving the golden rule

- `_assert_test_database_url`'s "name must contain 'test'" check still applies to every database
  name this design introduces: the template (`mlb_test_template`) and every clone
  (`mlb_test_<hex>`). No new code path in this design ever computes a database name without that
  substring, and the guard itself is not modified.
- `postgresql_noproc` only supplies *connection coordinates to a server* (host/port/user) — it is
  not, by itself, a guarantee about which database gets touched. The existing guard function
  (or an equivalent check applied to the resolved template/clone name before any DDL runs) is
  still the thing doing that job, and must run against every name this design generates, not just
  the original `TEST_DATABASE_URL`.

### 4. CI

- The same `postgresql_noproc` + `load` + clone code path serves CI as-is: GitHub's Postgres
  service container is, from pytest's point of view, just another "already-running server" —
  no separate CI-only branch in `conftest.py`.
- Splitting `.github/workflows/ci.yml`'s single linear job into parallel jobs (lint/mypy in one,
  unit tests in a second, integration tests in a third) is a standard, independent improvement —
  plain GitHub Actions `jobs:`, no new tooling, no cost. Tracked in this spec as a second,
  smaller implementation slice, not blocking the pytest-postgresql adoption.

## Non-goals for this spec (deferred, tracked, not abandoned)

Raised in the same conversation, explicitly separate projects:

- Adopting more Postgres extensions generally.
- Per-database-action benchmarking/timing with logged metadata.
- A full audit log of all database changes and configuration history.
- `conform.py`'s own runtime (step timing, `ANALYZE` calls) — evaluated this session, explicitly
  deferred; owner chose "neither yet" for that track.

## CLAUDE.md addition (owner-requested)

Add a directive to check for established, well-adopted patterns/libraries before hand-rolling a
bespoke solution to a cross-cutting problem (testing infra, auth, migrations, etc.), citing what
was found — worded as a checkable practice, not a slogan. Exact wording to be finalized and
committed alongside the implementation PR for this spec.

## Testing this change itself

- A test verifying two concurrent (simulated) `pytest`-style sessions get distinct, non-colliding
  database names and that the template-staleness lock correctly serializes a concurrent rebuild
  attempt rather than racing.
- A test that `_assert_test_database_url`-equivalent protection still rejects a non-test-named
  target for the template and for a generated clone name.
- A test that a crashed/orphaned clone (simulated) doesn't block a fresh session from starting
  (the core problem this spec fixes) and is picked up by the reaper/health check.
- Existing `db_conn`/`drop_tables_after` behavior: covered by the existing test suite continuing
  to pass unchanged against the new fixture plumbing — this design is meant to be invisible to
  the other 929 tests.

## Open questions to resolve before/during implementation

1. Does `UNLOGGED` survive `CREATE DATABASE ... TEMPLATE`? (verify empirically)
2. Exact `load` parameter semantics in the installed `pytest-postgresql` version — README and
   CHANGES disagree in places between versions on whether/how `load` callables are invoked;
   pin a version and confirm against its actual code, not just the README.
3. Where the orphan-reaping check lives (`mlb doctor` vs. a standalone script).
4. Exact CLAUDE.md wording for the "check for established patterns first" directive.
