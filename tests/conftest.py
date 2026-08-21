"""Shared fixtures for tests. Each pytest invocation gets its own isolated,
disposable database, built via pytest-postgresql's postgresql_noproc fixture
(see docs/superpowers/plans/2026-08-21-test-db-isolation.md) -- no database
is shared across concurrent test runs, so there is nothing to lock.
"""

import getpass
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

# Resolve the actual host/user/password ONCE, so postgresql_noproc (below)
# and TEST_DATABASE_URL (used everywhere else -- db_conn, _build_test_database,
# tests/integration/test_least_privilege.py, ...) can never diverge onto two
# different connections. This project's local Postgres uses Unix-socket peer
# auth for a bare `postgresql:///dbname` connection, which leaves host/user
# unset in _base_conninfo; TCP to "localhost" as the current OS user is
# confirmed to work locally via ~/.pgpass (keyed on the literal hostname
# "localhost", not "127.0.0.1" -- pytest_postgresql's own ini default), and
# this generalizes to any contributor running the same peer-auth setup under
# their own OS username: getpass.getuser() resolves that per-contributor, so
# no username is hardcoded here or in pyproject.toml.
_resolved_host = _base_conninfo.get("host") or "localhost"
_resolved_user = _base_conninfo.get("user") or getpass.getuser()
_resolved_password = _base_conninfo.get("password")

# Deviation from the original brief, verified empirically this session:
# factories.postgresql_noproc's own DatabaseJanitor (noprocess.py:99-122) is
# hardcoded to create the database as f"{dbname}_tmpl" with
# IS_TEMPLATE = true (NoopExecutor.template_dbname, executor_noop.py:60-63) --
# _RUN_DBNAME itself (no suffix) is never created by postgresql_noproc alone.
# That bare name is reserved for pytest_postgresql's separate, function-scoped
# `postgresql(...)` client fixture, which clones a fresh copy from the
# template per test -- not what this project wants (one persistent database
# for the whole run). Confirmed directly: connecting to plain _RUN_DBNAME
# fails with "database ... does not exist", while f"{_RUN_DBNAME}_tmpl" is
# the exact dbname the `load=[_build_test_database]` callable below receives
# and successfully migrates. IS_TEMPLATE = true only marks a database
# eligible to seed `CREATE DATABASE ... TEMPLATE`; it does not block normal
# connections (datallowconn stays true), so using it directly as this run's
# working database is safe -- and postgresql_noproc's own janitor.drop()
# still tears it down at session end, same as any other database it creates.
TEST_DATABASE_URL = psycopg.conninfo.make_conninfo(
    _base_test_url,
    host=_resolved_host,
    user=_resolved_user,
    password=_resolved_password,
    dbname=f"{_RUN_DBNAME}_tmpl",
    application_name="mlb_test_suite",
)
_assert_test_database_url(TEST_DATABASE_URL)
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
    host=_resolved_host,
    port=_base_conninfo.get("port"),
    user=_resolved_user,
    password=_resolved_password,
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


@pytest.fixture(scope="session")
def _test_database(postgresql_noproc):
    """Depends on postgresql_noproc so pytest builds this run's isolated
    database (via _build_test_database above) before any test runs, and
    drops it after the session ends -- both handled by the library's
    DatabaseJanitor, not by this fixture.
    """
    yield
    os.environ.pop("MLB_TEST_SUITE", None)


@pytest.fixture
def db_conn(_test_database):
    # Deliberately NOT autocommit — matches mlb_baseball.db.get_connection()
    # exactly, so tests exercise the same transaction semantics production
    # code actually runs under (this is what the track_run regression test
    # in test_ingest_tracking.py depends on to be meaningful).
    with psycopg.connect(TEST_DATABASE_URL) as conn:
        yield conn


@pytest.fixture
def drop_tables_after(db_conn):
    """Yields a `register(table_name)` function; every registered table is
    dropped after the test, regardless of pass/fail, so tests don't leak
    state into each other.

    Drops through the *same* db_conn a test used to create/read the table —
    not a second connection. A second connection's DROP TABLE would block
    forever on any lock db_conn is still holding from an uncommitted read
    (non-autocommit, see above), since db_conn's own teardown — which would
    release that lock — runs after this fixture's teardown, not before.
    """
    created: list[str] = []

    def register(table_name: str) -> str:
        created.append(table_name)
        return table_name

    yield register

    if created:
        db_conn.rollback()  # drop any lingering read-only transaction first
        with db_conn.cursor() as cur:
            for table in created:
                cur.execute(f"DROP TABLE IF EXISTS {table}")
        db_conn.commit()
