"""Shared fixtures. Integration tests run against a real, dedicated test
database (mlb_test) — never the real mlb database — consistent with this
project's "test against real Postgres, not mocks" approach (see CLAUDE.md).
"""

import os

import psycopg
import pytest
from psycopg import sql

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "postgresql:///mlb_test")


@pytest.fixture
def db_url_for():
    """Returns a function mapping a database name to TEST_DATABASE_URL with
    only the dbname swapped — so tests that need a second, disposable
    database (the "fresh unmigrated clone" tests) inherit whatever host/
    port/credentials the environment actually uses. Hardcoding
    postgresql:///<name> worked locally (unix socket, peer auth) but broke
    in CI, where Postgres is a TCP service container with password auth.
    A fixture, not an importable helper, because tests/ is not a package."""

    def _url(dbname: str) -> str:
        params = psycopg.conninfo.conninfo_to_dict(TEST_DATABASE_URL)
        params["dbname"] = dbname
        return psycopg.conninfo.make_conninfo(**params)

    return _url


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
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    from mlb_baseball import migrate

    migrate.run()
    _speed_up_test_database(TEST_DATABASE_URL)
    yield


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
