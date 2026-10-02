"""`ingest.table_totals` against real PostgreSQL: exact counts and a real statement timeout."""

import threading

import psycopg
import pytest
from psycopg.conninfo import make_conninfo

from mlb_baseball.ingest import table_totals


@pytest.fixture
def connect(db_conn):
    conninfo = make_conninfo(db_conn.info.dsn, password=db_conn.info.password)
    return lambda: psycopg.connect(conninfo)


def test_counts_exactly_and_marks_missing_or_odd_names_not_counted(
    db_conn, drop_tables_after, connect
):
    table = drop_tables_after("public.totals_probe")
    with db_conn.cursor() as cur:
        cur.execute(f"CREATE TABLE {table} (n int)")
        cur.execute(f"INSERT INTO {table} SELECT generate_series(1, 7)")
    db_conn.commit()

    totals = table_totals([table, "public.does_not_exist", "not a table; drop"], connect=connect)

    assert totals == {table: 7, "public.does_not_exist": None, "not a table; drop": None}


def test_a_blocked_count_times_out_and_prints_none_without_a_guess(
    db_conn, drop_tables_after, connect
):
    table = drop_tables_after("public.totals_locked")
    with db_conn.cursor() as cur:
        cur.execute(f"CREATE TABLE {table} (n int)")
        cur.execute(f"INSERT INTO {table} VALUES (1)")
    db_conn.commit()

    # Hold an exclusive lock from the fixture's own connection so count(*) blocks.
    with db_conn.cursor() as cur:
        cur.execute(f"LOCK TABLE {table} IN ACCESS EXCLUSIVE MODE")
    result: dict[str, int | None] = {}
    worker = threading.Thread(
        target=lambda: result.update(table_totals([table], timeout_seconds=0.5, connect=connect))
    )
    worker.start()
    worker.join(timeout=20)
    db_conn.rollback()

    assert not worker.is_alive()
    assert result == {table: None}
