"""Shared fixtures. Integration tests run against a real, dedicated test
database (mlb_test) — never the real mlb database — consistent with this
project's "test against real Postgres, not mocks" approach (see CLAUDE.md).
"""

import os

import psycopg
import pytest

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


@pytest.fixture(scope="session", autouse=True)
def _test_database():
    """Points DATABASE_URL at the test database and applies migrations once
    per test session, before any test runs."""
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    from mlb_baseball import migrate

    migrate.run()
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
