# Test Database Isolation (pytest-postgresql) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `tests/conftest.py`'s single shared `mlb_test` database + global advisory lock with one isolated, disposable database per `pytest` invocation, built via the `pytest-postgresql` library's `postgresql_noproc` fixture — so any number of agents/worktrees can run the full suite concurrently with no lock and no manual recovery from a stuck session.

**Architecture:** `pytest_postgresql.factories.postgresql_noproc(...)`, configured with an explicit host/port/user/password (parsed from the existing `TEST_DATABASE_URL`) and a high-entropy per-process `dbname`, replaces the hand-rolled lock/shared-database fixture. A `load` callable (`_build_test_database`) plugs `migrate.run()` and the existing `_speed_up_test_database` tweaks in as "how to populate this run's database" — the library owns database creation, connection-termination, and teardown (`DatabaseJanitor`); this project only supplies connection coordinates and the migration/tweak step.

**Tech Stack:** `pytest-postgresql==8.1.0` (verified installed and its exact source read this session — not assumed from README), `psycopg` v3 (already in use), Postgres 16 (already in use).

**Spec:** `docs/superpowers/specs/2026-08-21-test-db-isolation-design.md`. This plan corrects three points in that spec after reading the library's actual installed source (`.venv/lib/python3.12/site-packages/pytest_postgresql/`, this session): (1) no custom template-staleness hash/lock is needed — `postgresql_noproc` already builds-and-tears-down one database per session; (2) there is no "skip re-running migrations when unchanged" saving — every run still pays `migrate.run()` once, same as today; (3) orphan reaping uses "zero active connections" as the signal, not an age threshold — a session's teardown always drops its own database on clean exit, so a same-pattern database with no connections is definitionally orphaned.

## Global Constraints

- Database naming: every database this plan creates or references must contain the substring `test` (CLAUDE.md golden rule / `_assert_test_database_url`) — verified at every name-generation point, not just the original configured URL.
- No paid dependency, no new hosting, no cost (CLAUDE.md "$0/month budget").
- `tests/conftest.py`'s `_assert_test_database_url` guard is never weakened or removed — it is extended to cover new names this plan introduces, not bypassed.
- Existing fixture behavior (`db_conn`, `drop_tables_after`, `MLB_TEST_SUITE` env var) must remain observably identical to the other 929 tests — this plan changes *how* the database is built and named, not the connection semantics tests already rely on.
- Every step must be run for real and its actual output checked — this project's own "Definition of done" (CLAUDE.md) requires tests to actually pass, not be asserted.

---

## Task 1: Pin the dependency

**Files:**
- Modify: `pyproject.toml` (`[project.optional-dependencies].dev`)
- Modify: `uv.lock` (via `uv sync`)

**Interfaces:**
- Produces: `pytest_postgresql` importable at `pytest-postgresql>=8.1,<9` in the `dev` extra.

- [ ] **Step 1: Add the dependency**

Already staged in this worktree via `uv add --optional dev "pytest-postgresql"`. Confirm the exact pin in `pyproject.toml`:

```toml
dev = [
    "pytest>=8.0",
    "pytest-cov>=5.0",
    "ruff>=0.6",
    "mypy>=1.10",
    "pre-commit>=4.6",
    "sqlmesh[postgres]>=0.236.1",
    "sqlfluff>=3.0",
    "pytest-postgresql>=8.1,<9",
]
```

- [ ] **Step 2: Sync and verify import**

Run: `uv sync --extra dev && uv run python -c "import pytest_postgresql; print(pytest_postgresql.__file__)"`
Expected: prints a path under `.venv/lib/.../site-packages/pytest_postgresql/__init__.py`, no error.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "deps: add pytest-postgresql for per-run test database isolation"
```

---

## Task 2: Rewrite `tests/conftest.py`'s database fixture

**Files:**
- Modify: `tests/conftest.py:1-184` (everything from the module-level `TEST_DATABASE_URL` computation through the `_test_database` fixture; `db_conn` and `drop_tables_after`, lines 187-223, are unchanged)
- Test: `tests/integration/test_database_isolation.py` (new — see Task 4, written together with this task since they prove the same behavior)

**Interfaces:**
- Consumes: `mlb_baseball.migrate.run() -> list[str]` (existing, unchanged signature).
- Produces: `TEST_DATABASE_URL: str` (module-level constant, same name as today, now pointing at this run's unique database — everything downstream that reads it, e.g. `db_conn`, `tests/integration/test_least_privilege.py`'s own module-level `os.environ.get("TEST_DATABASE_URL")`, keeps working unchanged because this module sets `os.environ["TEST_DATABASE_URL"]` at *import* time, before any other test module is collected).

**Why this design (verified against `pytest_postgresql` source this session, not the README):**
- `factories.postgresql_noproc(...)`'s returned fixture is hardcoded `@pytest.fixture(scope="session")` (`noprocess.py:63`) — exactly the granularity wanted (one database per whole `pytest` invocation), no manual scope-wrangling needed.
- Its `DatabaseJanitor` (`janitor.py`) does `CREATE DATABASE "{dbname}"` on fixture setup and `DROP DATABASE IF EXISTS "{dbname}"` on teardown (after first terminating any connections and disabling new ones) — this is the exact create/migrate/teardown lifecycle this project wants, using the library's tested code, not hand-rolled DDL.
- Its `load` callables are invoked with keyword args `host, port, user, dbname, password` (`janitor.py:111-128`) *after* the database already exists — this project's loader just needs to connect using those and run `migrate.run()` + the existing speed tweaks.
- The library's ini defaults (`postgresql_host="127.0.0.1"`, `postgresql_user="postgres"`, confirmed in `plugin.py`) do **not** match this project's local Unix-socket peer-auth setup — every connection parameter must be passed explicitly, derived from the already-configured `TEST_DATABASE_URL`.

- [ ] **Step 1: Write the new fixture module code**

Replace `tests/conftest.py` lines 1-184 with:

```python
"""Shared fixtures for tests. Each pytest invocation gets its own isolated,
disposable database, built via pytest-postgresql's postgresql_noproc fixture
(see docs/superpowers/plans/2026-08-21-test-db-isolation.md) -- no database
is shared across concurrent test runs, so there is nothing to lock.
"""

import os
import secrets

import psycopg
import pytest
from dotenv import load_dotenv
from psycopg import sql
from pytest_postgresql import factories

load_dotenv()


def _assert_test_database_url(url: str) -> None:
    """Refuse the suite before it can mutate a non-disposable database."""
    dbname = str(psycopg.conninfo.conninfo_to_dict(url).get("dbname") or "")
    if "test" not in dbname.lower():
        raise RuntimeError(
            "TEST_DATABASE_URL must name a disposable test database; "
            f"refusing to run against {dbname or '<unspecified>'!r}"
        )


_base_test_url = os.environ.get("TEST_DATABASE_URL", "postgresql:///mlb_test")
_assert_test_database_url(_base_test_url)
_base_conninfo = psycopg.conninfo.conninfo_to_dict(_base_test_url)

# One high-entropy database name per pytest process -- not per test, not per
# xdist worker within a process (this project has no xdist parallelism
# today). Any number of concurrent `pytest` invocations (separate agent
# worktrees) each get their own name and never collide.
_RUN_DBNAME = f"mlb_test_{secrets.token_hex(6)}"
_assert_test_database_url(f"postgresql:///{_RUN_DBNAME}")

TEST_DATABASE_URL = psycopg.conninfo.make_conninfo(
    _base_test_url,
    dbname=_RUN_DBNAME,
    application_name="mlb_test_suite",
)
# Set at *import* time, not inside a fixture -- tests/conftest.py is always
# imported before any test module under tests/ is collected, so any test
# file reading os.environ["TEST_DATABASE_URL"] at its own module level
# (e.g. tests/integration/test_least_privilege.py) already sees this run's
# real database name, not the base-configured one.
os.environ["TEST_DATABASE_URL"] = TEST_DATABASE_URL


def _speed_up_test_database(url: str) -> None:
    """Test-only durability relaxations for the disposable database at
    `url` -- never called against production (this only ever runs from the
    postgresql_noproc load callable below, which always targets this run's
    own database). See GitHub issue #2 and README "Testing" for the full
    measurement.

    Two independent changes, both needed:

    1. `synchronous_commit = off` -- every test's commit otherwise waits on
       a WAL flush it doesn't need for disposable data.

    2. UNLOGGED on every core.play/core.pitch season partition (migration
       0011; ~316 partitions combined). Confirmed directly (psql \\timing
       + pg_stat_activity) that TRUNCATE on these is dominated by a
       synchronous per-relation fsync (`DataFileImmediateSync` wait), and
       that this is *independent* of synchronous_commit. Unlogged relations
       skip that fsync (they're wiped on crash recovery anyway, which is
       fine -- test data is always rebuilt).
    """
    with psycopg.connect(url, autocommit=True) as conn:
        dbname = conn.info.dbname
        alter_db = sql.SQL("ALTER DATABASE {} SET synchronous_commit = off")
        conn.execute(alter_db.format(sql.Identifier(dbname)))
        conn.execute("SET synchronous_commit = off")
        partitions = conn.execute(
            """
            SELECT n.nspname, c.relname
            FROM pg_inherits i
            JOIN pg_class c ON c.oid = i.inhrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            JOIN pg_class p ON p.oid = i.inhparent
            JOIN pg_namespace pn ON pn.oid = p.relnamespace
            WHERE pn.nspname = 'core'
              AND p.relname IN ('play', 'pitch')
              AND c.relpersistence <> 'u'
            """
        ).fetchall()
        for schema_name, table_name in partitions:
            conn.execute(
                sql.SQL("ALTER TABLE {}.{} SET UNLOGGED").format(
                    sql.Identifier(schema_name), sql.Identifier(table_name)
                )
            )


def _build_test_database(
    host: str, port: int, user: str, dbname: str, password: str | None
) -> None:
    """pytest-postgresql `load` callable -- runs once, after postgresql_noproc
    has already created `dbname` (empty). Builds this run's real schema and
    applies the same test-only speed tweaks the old shared-database fixture
    applied once per session -- just retargeted at this run's own database.
    """
    dsn = psycopg.conninfo.make_conninfo(
        host=host, port=port, user=user, password=password, dbname=dbname
    )
    os.environ["DATABASE_URL"] = dsn
    os.environ["MLB_TEST_SUITE"] = "1"

    from mlb_baseball import migrate

    migrate.run()
    _speed_up_test_database(dsn)


postgresql_noproc = factories.postgresql_noproc(
    host=_base_conninfo.get("host"),
    port=_base_conninfo.get("port"),
    user=_base_conninfo.get("user"),
    password=_base_conninfo.get("password"),
    dbname=_RUN_DBNAME,
    load=[_build_test_database],
)


class _UndefinedTableCursor:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def execute(self, *args, **kwargs):
        raise psycopg.errors.UndefinedTable("relation does not exist")


class _UnmigratedConnection:
    """Minimal DB-API context manager for unmigrated-DB error-path tests."""

    def __init__(self):
        self.rolled_back = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def cursor(self):
        return _UndefinedTableCursor()

    def rollback(self):
        self.rolled_back = True


@pytest.fixture
def unmigrated_db_connection():
    """A connection that raises the real missing-table exception on query."""

    return _UnmigratedConnection()


@pytest.fixture(scope="session", autouse=True)
def _test_database(postgresql_noproc):
    """Depends on postgresql_noproc so pytest builds this run's isolated
    database (via _build_test_database above) before any test runs, and
    drops it after the session ends -- both handled by the library's
    DatabaseJanitor, not by this fixture.
    """
    yield
    os.environ.pop("MLB_TEST_SUITE", None)
```

Note: `host`/`port`/`user`/`password` passed to `factories.postgresql_noproc(...)` may legitimately be `None` when `_base_test_url` doesn't specify them (e.g. local `postgresql:///mlb_test` peer-auth style) — `factories.postgresql_noproc`'s own fallback (`host or config.host`) would substitute the library's ini default (`127.0.0.1`/`postgres` user) in that case, which is **wrong** for this project. Step 2 below verifies this empirically for the actual local setup; if it fails, add explicit `postgresql_host`/`postgresql_user` entries to `pyproject.toml`'s `[tool.pytest.ini_options]` matching the real local Postgres role instead of leaving it to fall through to the library's defaults.

- [ ] **Step 2: Run the full existing suite against the new fixture**

Run: `uv run pytest -q`
Expected: all currently-passing tests still pass (929 of 931 — the two lock-contention tests fail here, expected; fixed in Task 4). Watch specifically for a connection/auth error on the very first test — if one occurs, it confirms the host/user fallback problem noted above; add explicit `postgresql_host = "localhost"` / `postgresql_user = "<the value _base_conninfo lacked>"` to `[tool.pytest.ini_options]` in `pyproject.toml` and rerun.

- [ ] **Step 3: Confirm the database is actually dropped after the run**

Run: `uv run pytest -q tests/unit/test_config.py && psql postgresql:///postgres -c "SELECT datname FROM pg_database WHERE datname LIKE 'mlb_test_%'"`
Expected: no rows (the run's database was created and dropped within that single `pytest` invocation).

- [ ] **Step 4: Commit**

```bash
git add tests/conftest.py
git commit -m "test: replace shared mlb_test database + global lock with a per-run isolated database (pytest-postgresql)"
```

---

## Task 3: Fix `scripts/verify_sqlmesh_candidate.py`'s hardcoded database name

**Files:**
- Modify: `scripts/verify_sqlmesh_candidate.py:44-46`
- Test: `tests/integration/test_sqlmesh_candidate_gate.py` (existing, unchanged — proves the fix)

**Why:** this script hard-fails with `conn.info.dbname != "mlb_test"` (line 45). Under Task 2's design, the database the test suite actually uses is named `mlb_test_<12 hex chars>`, never literally `mlb_test` — this check would reject every run. Found by reading the script directly this session, not guessed.

**Interfaces:**
- Consumes: nothing new.
- Produces: nothing new — same CLI contract, just a loosened safety check.

- [ ] **Step 1: Run the existing test to see it fail for the right reason**

Run: `uv run pytest tests/integration/test_sqlmesh_candidate_gate.py -v`
Expected (before the fix, after Task 2 lands): FAIL with `SystemExit: candidate gate only permits the existing mlb_test database`.

- [ ] **Step 2: Loosen the check**

In `scripts/verify_sqlmesh_candidate.py`, replace:

```python
        if conn.info.dbname != "mlb_test":
            raise SystemExit("candidate gate only permits the existing mlb_test database")
```

with:

```python
        if not conn.info.dbname.startswith("mlb_test"):
            raise SystemExit("candidate gate only permits an mlb_test-named database")
```

- [ ] **Step 3: Run the test again to confirm it passes**

Run: `uv run pytest tests/integration/test_sqlmesh_candidate_gate.py -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add scripts/verify_sqlmesh_candidate.py
git commit -m "fix: sqlmesh candidate gate accepts any mlb_test-prefixed database, not only the literal name"
```

---

## Task 4: Replace the lock-contention test with an isolation test

**Files:**
- Delete: `tests/integration/test_conftest_lock_contention.py` (tests behavior — fail-fast on a shared lock — that no longer exists after Task 2)
- Create: `tests/integration/test_database_isolation.py`

**Why:** the deleted test asserts `result.returncode == 1` and `"already reserved by another test session" in combined` for a second concurrent `pytest` invocation. Under the new design there is no shared lock to collide on — a second concurrent invocation should *succeed* with its own database. This is the single most important behavior this whole plan exists to fix; it needs direct proof, not just "the old test was deleted."

**Interfaces:**
- Consumes: nothing new (subprocess-based, like the test it replaces).
- Produces: nothing new.

- [ ] **Step 1: Write the new test**

```python
"""Regression coverage proving concurrent pytest sessions no longer collide.

Real incident this replaces: before this change, tests/conftest.py's
mlb-test-suite advisory lock meant a second concurrent `pytest` invocation
against the same base configuration failed immediately (or, before an
earlier fix, hung silently). Each invocation now builds its own uniquely
named, disposable database, so two concurrent sessions must both succeed.
"""

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[2]


def test_concurrent_test_sessions_both_succeed_with_isolated_databases():
    # This test is itself running inside a pytest session that already has
    # its own isolated database (tests/conftest.py's postgresql_noproc
    # fixture, built before any test runs). A nested `uv run pytest`
    # invocation against the same base TEST_DATABASE_URL must build its
    # OWN separate database rather than colliding with this session's.
    env = os.environ.copy()

    result = subprocess.run(
        ["uv", "run", "pytest", "tests/unit/test_config.py", "-q"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "passed" in result.stdout
```

- [ ] **Step 2: Run it to verify it fails against the OLD conftest.py (sanity check, skip if Task 2 already landed)**

Only relevant if Task 2 hasn't been committed yet in this session's history; otherwise skip straight to Step 3.

- [ ] **Step 3: Run it for real**

Run: `uv run pytest tests/integration/test_database_isolation.py -v`
Expected: PASS. (This spawns a real second `pytest` process against a real second database — it is legitimately slower than a typical test; that's expected and correct, not a bug.)

- [ ] **Step 4: Delete the old test and commit both changes together**

```bash
git rm tests/integration/test_conftest_lock_contention.py
git add tests/integration/test_database_isolation.py
git commit -m "test: prove concurrent pytest sessions get isolated databases instead of colliding on a shared lock"
```

---

## Task 5: Orphan database reaper

**Files:**
- Create: `mlb_baseball/reap_test_databases.py` (selection logic — pure, unit-testable)
- Create: `scripts/reap_test_databases.py` (thin CLI entry point)
- Test: `tests/unit/test_reap_test_databases.py`

**Why here, not `mlb doctor`:** `mlb doctor`'s checks are about production data health (CLAUDE.md "Operational health checks" — table freshness, connector status). A leftover test database from a crashed `pytest` process is test-infrastructure hygiene, a different concern with a different owner (whoever's disk is filling up, not whoever's checking data freshness) — bolting it onto `doctor` would be scope creep into a module that already has a clear, different job. A small standalone script matches this project's existing `scripts/` pattern (e.g. `scripts/rehearse_sample.py`, `scripts/benchmark_mlb_api_ingestion.py`).

**Why "zero connections", not an age threshold:** a session's own teardown (`DatabaseJanitor.drop()`, Task 2) always drops its database when a `pytest` process exits cleanly. The *only* way an `mlb_test_<hex>` database can exist with zero active connections is a prior crash before that teardown ran — there is no legitimate "idle but still needed" state for one of these databases. A short recheck window (below) exists only to rule out the narrow race where a database was just created and hasn't been connected to yet.

**Interfaces:**
- Produces: `find_orphaned_test_databases(cur: psycopg.Cursor) -> list[str]` — pure function, takes a cursor, returns candidate database names (queries `pg_database` LEFT JOIN `pg_stat_activity`).
- Produces: `reap_orphaned_test_databases(dsn: str, *, recheck_delay_seconds: float = 5.0) -> list[str]` — connects, finds candidates twice (with a delay between), drops the intersection, returns what was dropped.

- [ ] **Step 1: Write the failing unit test for the selection logic**

```python
# tests/unit/test_reap_test_databases.py
from unittest.mock import MagicMock

from mlb_baseball.reap_test_databases import find_orphaned_test_databases


def test_finds_databases_matching_pattern_with_no_active_connections():
    cur = MagicMock()
    cur.execute.return_value = None
    cur.fetchall.return_value = [("mlb_test_abc123",), ("mlb_test_def456",)]

    result = find_orphaned_test_databases(cur)

    assert result == ["mlb_test_abc123", "mlb_test_def456"]
    (query, params), _ = cur.execute.call_args
    assert "mlb\\_test\\_%" in query or "mlb\\_test\\_%" in params
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/unit/test_reap_test_databases.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mlb_baseball.reap_test_databases'`.

- [ ] **Step 3: Write the module**

```python
# mlb_baseball/reap_test_databases.py
"""Drops per-run test databases (tests/conftest.py's postgresql_noproc
fixture, mlb_test_<hex>) left behind by a pytest process that crashed
before its own teardown ran. See
docs/superpowers/plans/2026-08-21-test-db-isolation.md Task 5.

Never touches `mlb`, or any database not matching the mlb_test_<hex>
naming pattern this project's test suite uses -- see CLAUDE.md's database
golden rule.
"""

import time

import psycopg

_PATTERN = "mlb\\_test\\_%"  # escaped for LIKE: literal underscores, not wildcards


def find_orphaned_test_databases(cur: psycopg.Cursor) -> list[str]:
    """Database names matching the per-run test naming pattern with zero
    currently active connections -- see module docstring for why zero
    connections is a sufficient, not just necessary, signal here."""
    cur.execute(
        """
        SELECT d.datname
        FROM pg_database d
        WHERE d.datname LIKE %s
          AND NOT EXISTS (
              SELECT 1 FROM pg_stat_activity a WHERE a.datname = d.datname
          )
        ORDER BY d.datname
        """,
        (_PATTERN,),
    )
    return [row[0] for row in cur.fetchall()]


def reap_orphaned_test_databases(
    dsn: str, *, recheck_delay_seconds: float = 5.0
) -> list[str]:
    """Drops databases still orphaned after two checks `recheck_delay_seconds`
    apart -- rules out the narrow race of a database just created by a
    session that hasn't connected to it yet."""
    with psycopg.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            first_pass = set(find_orphaned_test_databases(cur))
        if not first_pass:
            return []

        time.sleep(recheck_delay_seconds)

        with conn.cursor() as cur:
            second_pass = set(find_orphaned_test_databases(cur))

        still_orphaned = sorted(first_pass & second_pass)
        with conn.cursor() as cur:
            for dbname in still_orphaned:
                cur.execute(f'DROP DATABASE IF EXISTS "{dbname}"')
    return still_orphaned
```

- [ ] **Step 4: Run the unit test again to verify it passes**

Run: `uv run pytest tests/unit/test_reap_test_databases.py -v`
Expected: PASS.

- [ ] **Step 5: Write the CLI entry point**

```python
# scripts/reap_test_databases.py
#!/usr/bin/env python3
"""Drop orphaned per-run test databases left behind by a crashed pytest
process. Safe to run any time, including while other test sessions are
active -- see mlb_baseball/reap_test_databases.py for why.

Usage:
    TEST_DATABASE_URL=postgresql:///mlb_test uv run python scripts/reap_test_databases.py
"""

import os

from mlb_baseball.reap_test_databases import reap_orphaned_test_databases


def main() -> None:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        raise SystemExit("set TEST_DATABASE_URL (used only for host/port/user, not the dbname)")
    dropped = reap_orphaned_test_databases(url)
    if dropped:
        print(f"dropped {len(dropped)} orphaned test database(s): {', '.join(dropped)}")
    else:
        print("no orphaned test databases found")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Manual smoke test against a real orphan**

Run:
```bash
psql postgresql:///postgres -c "CREATE DATABASE mlb_test_smoketest123"
uv run python scripts/reap_test_databases.py
psql postgresql:///postgres -c "SELECT datname FROM pg_database WHERE datname = 'mlb_test_smoketest123'"
```
Expected: script prints `dropped 1 orphaned test database(s): mlb_test_smoketest123`; the final query returns no rows.

- [ ] **Step 7: Commit**

```bash
git add mlb_baseball/reap_test_databases.py scripts/reap_test_databases.py tests/unit/test_reap_test_databases.py
git commit -m "feat: add orphaned test database reaper for crashed pytest sessions"
```

---

## Task 6: Update README "Testing" section

**Files:**
- Modify: `README.md` (the "Testing" section — locate via `grep -n "^## Testing" README.md`)

- [ ] **Step 1: Update the documented behavior**

Read the current section first (`grep -n -A15 "^## Testing" README.md`), then replace any description of the single shared `mlb_test` database + advisory-lock reservation with a short description of the new behavior: each `pytest` invocation builds and tears down its own isolated database automatically (via `pytest-postgresql`); `TEST_DATABASE_URL` in `.env` still names the base connection (host/port/user/password) tests connect through, but the actual database used each run is a uniquely-named clone, not `mlb_test` itself; concurrent runs (including multiple agent worktrees) no longer collide. Mention `scripts/reap_test_databases.py` for cleaning up after a crashed run.

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: describe per-run isolated test databases, replacing the old shared-lock description"
```

---

## Task 7: Split CI into parallel jobs

**Files:**
- Modify: `.github/workflows/ci.yml`

**Why:** today's single `test` job runs lint → sqlfluff → mypy → Chadwick build → full pytest suite, linearly, ~5-6 minutes before any feedback on a trivial lint error. Splitting lint/type-checks into their own job means that feedback arrives in under a minute, independent of the slower integration-test job. This does not depend on Tasks 1-6 (CI already gets a fresh Postgres service container per run — it was never part of the lock-contention problem) and can be implemented and merged independently.

**Interfaces:**
- Produces: three independent jobs (`lint`, `unit`, `integration`) alongside the existing `secrets` job, replacing today's single `test` job.

- [ ] **Step 1: Split the `test` job into `lint`, `unit`, `integration`**

Replace the single `test:` job in `.github/workflows/ci.yml` with:

```yaml
  lint:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false

      - uses: astral-sh/setup-uv@37802adc94f370d6bfd71619e3f0bf239e1f3b78 # v7.6.0
        with:
          python-version: "3.11"
          enable-cache: true

      - name: Install package with dev dependencies
        run: uv sync --frozen --extra dev

      - name: Lint (ruff)
        run: uv run ruff check .

      - name: Lint (sqlfluff, mlb_baseball/sql/)
        run: uv run sqlfluff lint mlb_baseball/sql/

      - name: Type-check (mypy)
        run: uv run mypy

  unit:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false

      - uses: astral-sh/setup-uv@37802adc94f370d6bfd71619e3f0bf239e1f3b78 # v7.6.0
        with:
          python-version: "3.11"
          enable-cache: true

      - name: Install package with dev dependencies
        run: uv sync --frozen --extra dev

      - name: Run unit tests
        run: uv run pytest tests/unit -q --cov=mlb_baseball --cov-report=xml

      - name: Upload coverage to Codecov
        if: always()
        uses: codecov/codecov-action@fb8b3582c8e4def4969c97caa2f19720cb33a72f # v7.0.0
        with:
          files: coverage.xml
          flags: unit
          fail_ci_if_error: false

  integration:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: postgres
          POSTGRES_PASSWORD: postgres
          POSTGRES_DB: mlb_test
        ports:
          - 5432:5432
        options: >-
          --health-cmd "pg_isready -U postgres"
          --health-interval 5s
          --health-timeout 5s
          --health-retries 10

    permissions:
      contents: read

    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false

      - uses: astral-sh/setup-uv@37802adc94f370d6bfd71619e3f0bf239e1f3b78 # v7.6.0
        with:
          python-version: "3.11"
          enable-cache: true

      - name: Install package with dev dependencies
        run: uv sync --frozen --extra dev

      - name: Enable pg_stat_statements in the Postgres service
        env:
          POSTGRES_CONTAINER_ID: ${{ job.services.postgres.id }}
        run: |
          docker exec "$POSTGRES_CONTAINER_ID" psql -U postgres -c \
            "ALTER SYSTEM SET shared_preload_libraries = 'pg_stat_statements'"
          docker restart "$POSTGRES_CONTAINER_ID"
          until docker exec "$POSTGRES_CONTAINER_ID" pg_isready -U postgres; do sleep 1; done

      - name: Cache Chadwick tools build
        id: chadwick-cache
        uses: actions/cache@55cc8345863c7cc4c66a329aec7e433d2d1c52a9 # v6.1.0
        with:
          path: ~/chadwick-install
          key: chadwick-${{ env.CHADWICK_REF }}

      - name: Build Chadwick tools (cwevent/cwgame/cwbox)
        if: steps.chadwick-cache.outputs.cache-hit != 'true'
        run: |
          sudo apt-get install -y -q autoconf automake libtool
          git clone https://github.com/chadwickbureau/chadwick.git
          cd chadwick
          git checkout "$CHADWICK_REF"
          autoreconf -i
          ./configure --prefix="$HOME/chadwick-install"
          make -j2
          make install

      - name: Install Chadwick tools onto PATH
        run: |
          echo "$HOME/chadwick-install/bin" >> "$GITHUB_PATH"

      - name: Run integration tests
        env:
          TEST_DATABASE_URL: postgresql://postgres:postgres@localhost:5432/mlb_test
          DATABASE_URL: postgresql://postgres:postgres@localhost:5432/mlb_test
        run: uv run pytest tests/integration -q --cov=mlb_baseball --cov-report=xml

      - name: Upload coverage to Codecov
        if: always()
        uses: codecov/codecov-action@fb8b3582c8e4def4969c97caa2f19720cb33a72f # v7.0.0
        with:
          files: coverage.xml
          flags: integration
          fail_ci_if_error: false
```

Also update the file's top comment (lines 1-17) to describe three parallel jobs instead of one linear job.

- [ ] **Step 2: Push and verify on a real CI run**

Run: `git push` (on this task's branch), then `gh run watch` (or `gh run list --limit 1` then `gh run view <id>`).
Expected: `secrets`, `lint`, `unit`, `integration` all run concurrently (not one after another) and all pass. `lint` and `unit` should finish well before `integration`.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: split lint/unit/integration into parallel jobs for faster feedback"
```

---

## Task 8: CLAUDE.md directive

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add the directive**

Add a new subsection under "Scope discipline" (or as its own short section near it):

```markdown
## Check for established solutions first

Before designing a bespoke solution to a cross-cutting infrastructure problem (test isolation,
auth, migrations, CI orchestration, and similar), check whether a well-adopted library or pattern
already solves it, and say what was found before proposing a hand-rolled alternative. Prefer the
established tool unless there's a concrete, stated reason it doesn't fit — "we'd rather write it
ourselves" is not that reason.
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add directive to check for established solutions before hand-rolling cross-cutting infra"
```

---

## Self-review notes (fixed inline while writing this plan, not left as TODOs)

- **Spec coverage:** all of the approved spec's items are covered — Task 2 (per-run isolation), Task 2 (safety guard preserved and extended), Task 5 (orphan reaping — redesigned from an age threshold to a zero-connections check, a real improvement found while researching `pg_database`'s lack of a creation timestamp), Task 7 (CI split), Task 8 (CLAUDE.md directive). The spec's narrow "template staleness lock" is *not* implemented — superseded by the simpler, verified-correct `postgresql_noproc` per-run lifecycle (see "Spec" section above for why).
- **Hidden dependency found and handled:** `scripts/verify_sqlmesh_candidate.py`'s hardcoded `!= "mlb_test"` check (Task 3) — not mentioned in the spec, found by reading the actual consumers of `TEST_DATABASE_URL` this session.
- **Ordering hazard found and handled:** `tests/integration/test_least_privilege.py` reads `TEST_DATABASE_URL` from `os.environ` at its own module import time — Task 2's design sets the resolved per-run URL into `os.environ` at `conftest.py` import time specifically so this keeps working with no changes to that file.
- **Type/name consistency:** `TEST_DATABASE_URL` (module constant name) and `_test_database` (fixture name) are kept identical to today's names throughout, since `db_conn`/`drop_tables_after` (unchanged) and other test files reference them by these exact names.
