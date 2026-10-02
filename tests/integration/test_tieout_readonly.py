"""The tie-out gate's database access is read-only and refuses the wrong database.

Real PostgreSQL (the disposable per-run test database), because read-only
transactions and ``current_database()`` are database semantics, not something
a mock can prove.
"""

import psycopg
import pytest

from mlb_baseball import tieout
from tests.conftest import TEST_DATABASE_URL


def _db_name(db_conn) -> str:
    with db_conn.cursor() as cur:
        cur.execute("SELECT current_database()")
        return cur.fetchone()[0]


def test_readonly_connection_reads_but_cannot_write(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("CREATE TABLE IF NOT EXISTS raw.tieout_probe (n integer)")
        cur.execute("INSERT INTO raw.tieout_probe VALUES (1)")
    db_conn.commit()
    try:
        conn = tieout.open_readonly(TEST_DATABASE_URL, expect_db=_db_name(db_conn))
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT n FROM raw.tieout_probe")
                assert cur.fetchall() == [(1,)]
            conn.rollback()
            for statement in (
                "INSERT INTO raw.tieout_probe VALUES (2)",
                "UPDATE raw.tieout_probe SET n = 9",
                "DELETE FROM raw.tieout_probe",
                "TRUNCATE raw.tieout_probe",
                "DROP TABLE raw.tieout_probe",
            ):
                with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
                    with conn.cursor() as cur:
                        cur.execute(statement)
                conn.rollback()
        finally:
            conn.close()
        with db_conn.cursor() as cur:
            cur.execute("SELECT n FROM raw.tieout_probe")
            assert cur.fetchall() == [(1,)]  # nothing above changed the table
    finally:
        db_conn.rollback()
        with db_conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS raw.tieout_probe")
        db_conn.commit()


def test_a_connection_to_the_wrong_database_is_refused_before_any_query(db_conn):
    with pytest.raises(tieout.TieOutError, match="expected 'mlb'"):
        tieout.open_readonly(TEST_DATABASE_URL, expect_db="mlb")


def test_the_statement_timeout_is_applied(db_conn):
    conn = tieout.open_readonly(
        TEST_DATABASE_URL, expect_db=_db_name(db_conn), statement_timeout_ms=1234
    )
    try:
        with conn.cursor() as cur:
            cur.execute("SHOW statement_timeout")
            assert cur.fetchone()[0] == "1234ms"
    finally:
        conn.close()


def test_fetch_series_builds_counts_from_a_real_query(db_conn):
    conn = tieout.open_readonly(TEST_DATABASE_URL, expect_db=_db_name(db_conn))
    try:
        series = tieout.fetch_series(
            conn,
            "probe",
            "game",
            ["k", "g"],
            "SELECT season, game_id, k, g FROM (VALUES "
            "(2019, 'ATL201904010', 12, 1), (2019, 'ATL201904020', 9, 1)) "
            "AS t(season, game_id, k, g) WHERE season = %(season)s",
            {"season": 2019},
        )
    finally:
        conn.close()

    assert series.counts == {
        ("2019", "ATL201904010"): {"k": 12, "g": 1},
        ("2019", "ATL201904020"): {"k": 9, "g": 1},
    }
