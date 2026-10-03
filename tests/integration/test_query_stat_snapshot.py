"""`snapshot_query_stats` copies pg_stat_statements into meta.query_stat_snapshot
and prunes old rows; a database without the extension is skipped, not an error."""

import psycopg
import pytest

from mlb_baseball import nightly


@pytest.fixture
def stats_db(db_conn):
    try:
        with db_conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS pg_stat_statements")
        db_conn.commit()
        with db_conn.cursor() as cur:
            # CREATE EXTENSION succeeds without the library preloaded; the view
            # then errors on read, so check it is actually readable.
            cur.execute("SELECT 1 FROM pg_stat_statements LIMIT 1")
    except psycopg.Error:
        db_conn.rollback()
        pytest.skip("pg_stat_statements is not usable in the test database")
    return db_conn


def test_snapshot_writes_rows_and_prunes_old_ones(stats_db):
    with stats_db.cursor() as cur:
        cur.execute("SELECT 1 + 1")  # make sure at least one statement is tracked
        cur.execute(
            "INSERT INTO meta.query_stat_snapshot VALUES "
            "(now() - interval '400 days', 1, 1, 1, 1, 1, 1, 1, 1, 'old')"
        )
    stats_db.commit()

    written = nightly.snapshot_query_stats()

    assert written is not None and written > 0
    with stats_db.cursor() as cur:
        cur.execute("SELECT count(*) FROM meta.query_stat_snapshot WHERE query = 'old'")
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT count(*) FROM meta.query_stat_snapshot")
        assert cur.fetchone()[0] == written


def test_missing_extension_is_skipped_not_fatal(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("DROP EXTENSION IF EXISTS pg_stat_statements")
    db_conn.commit()
    assert nightly.snapshot_query_stats() is None


def test_snapshot_table_accepts_a_null_query_text(db_conn):
    # PostgreSQL can keep a queryid and its counters while discarding the text.
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO meta.query_stat_snapshot VALUES (now(), 99, 1, 1, 1, 1, 1, 1, 1, NULL)"
        )
        cur.execute("SELECT query FROM meta.query_stat_snapshot WHERE queryid = 99")
        assert cur.fetchone()[0] is None
    db_conn.rollback()
