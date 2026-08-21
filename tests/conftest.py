"""Shared fixtures for tests that use the existing disposable test database.

Tests never create additional databases.  Most integration coverage uses the
database selected by ``TEST_DATABASE_URL``; the small number of tests for an
unmigrated database simulate PostgreSQL's missing-table error in-process.
"""

import os

import psycopg
import pytest
from dotenv import load_dotenv
from psycopg import sql

load_dotenv()

_test_database_url = os.environ.get("TEST_DATABASE_URL", "postgresql:///mlb_test")
_separator = "&" if "?" in _test_database_url else "?"
TEST_DATABASE_URL = f"{_test_database_url}{_separator}application_name=mlb_test_suite"


def _assert_test_database_url(url: str) -> None:
    """Refuse the suite before it can mutate a non-disposable database."""
    dbname = str(psycopg.conninfo.conninfo_to_dict(url).get("dbname") or "")
    if "test" not in dbname.lower():
        raise RuntimeError(
            "TEST_DATABASE_URL must name a disposable test database; "
            f"refusing to run against {dbname or '<unspecified>'!r}"
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


def _speed_up_test_database(url: str) -> None:
    """Test-only durability relaxations for the disposable database at
    `url` — never called against production (this only ever runs from the
    session fixture below, which always targets TEST_DATABASE_URL, never
    the DATABASE_URL production code paths use). See GitHub issue #2 and
    README "Testing" for the full measurement.

    Two independent changes, both needed:

    1. `synchronous_commit = off` — every test's commit otherwise waits on
       a WAL flush it doesn't need for disposable data. Free win for the
       suite's many small per-test transactions.

    2. UNLOGGED on every core.play/core.pitch season partition (migration
       0011; ~316 partitions combined). Confirmed directly (psql \\timing
       + pg_stat_activity) that TRUNCATE on these is dominated by a
       synchronous per-relation fsync (`DataFileImmediateSync` wait), and
       that this is *independent* of synchronous_commit — a bare TRUNCATE
       took ~79s with synchronous_commit on and ~84s with it off, no
       improvement. Unlogged relations skip that fsync (they're wiped on
       crash recovery anyway, which is fine — test data is always
       rebuilt), dropping the same TRUNCATE to ~20s. Idempotent and cheap
       (~0.2s total) once already set, so this runs unconditionally on
       every session start rather than only on a fresh database.
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


@pytest.fixture(scope="session", autouse=True)
def _test_database():
    """Points DATABASE_URL at the test database, applies migrations once
    per test session before any test runs, then applies test-only
    durability relaxations (never done against production — see
    _speed_up_test_database's docstring)."""
    _assert_test_database_url(TEST_DATABASE_URL)
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    from mlb_baseball import migrate

    # Keep an exclusive, session-scoped reservation for the entire test run.
    # Normal project ingestion/conform/model workflows check this lock before
    # starting, so they fail cleanly instead of deadlocking test fixture DDL.
    #
    # Non-blocking (pg_try_advisory_lock), not the blocking pg_advisory_lock:
    # two test sessions racing for mlb_test used to mean the second one just
    # hung silently -- often for the other session's entire multi-minute run
    # -- with zero indication of what it was waiting on or why. Failing
    # immediately with who's holding it is strictly more useful than an
    # opaque wait, especially for an agent (not a human watching a
    # terminal) deciding whether to wait, investigate, or back off.
    with psycopg.connect(TEST_DATABASE_URL) as reservation:
        acquired = reservation.execute(
            "SELECT pg_try_advisory_lock(hashtext('mlb-test-suite'))"
        ).fetchone()[0]
        if not acquired:
            holder = reservation.execute(
                """
                SELECT a.pid, a.application_name, a.state, a.query_start
                FROM pg_locks l
                JOIN pg_stat_activity a ON a.pid = l.pid
                WHERE l.locktype = 'advisory'
                  AND l.objid = hashtext('mlb-test-suite')::oid
                  AND l.granted AND a.pid <> pg_backend_pid()
                """
            ).fetchone()
            detail = (
                f"pid {holder[0]} ({holder[1]!r}, {holder[2]}, running since {holder[3]})"
                if holder
                else "an unidentified session"
            )
            pytest.exit(
                f"{TEST_DATABASE_URL!r} is already reserved by another test session -- "
                f"{detail}. Wait for it to finish before running tests against the same "
                "database, or point TEST_DATABASE_URL at a different disposable database "
                "if you deliberately need to run concurrently.",
                returncode=1,
            )
        os.environ["MLB_TEST_SUITE"] = "1"
        try:
            migrate.run()
            _speed_up_test_database(TEST_DATABASE_URL)
            yield
        finally:
            os.environ.pop("MLB_TEST_SUITE", None)


@pytest.fixture
def db_conn():
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
