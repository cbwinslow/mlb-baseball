import uuid

import psycopg

from mlb_baseball.health import (
    check_last_run,
    check_recent_run,
    check_table_exists,
    check_table_has_rows,
)


def test_check_table_has_rows_true_when_populated(db_conn, drop_tables_after):
    table = drop_tables_after("raw.test_health_widgets")
    with db_conn.cursor() as cur:
        cur.execute(f"CREATE TABLE {table} (id int)")
        cur.execute(f"INSERT INTO {table} VALUES (1)")
    db_conn.commit()

    result = check_table_has_rows(table)

    assert result.ok
    assert "1 rows" in result.detail


def test_check_table_has_rows_false_when_table_never_created():
    # A registered connector's health_check() can run before that connector
    # has ever been bootstrapped (e.g. right after a fresh clone + migrate) —
    # this must report cleanly instead of crashing with UndefinedTable, which
    # used to take down the entire `mlb doctor` run (see doctor.py's per-
    # connector try/except).
    result = check_table_has_rows("raw.test_health_never_created")

    assert not result.ok
    assert "never bootstrapped" in result.detail

    # Calling it again must still work cleanly too (no lingering bad state).
    result_again = check_table_has_rows("raw.test_health_never_created")
    assert not result_again.ok


def test_check_table_has_rows_false_when_empty(db_conn, drop_tables_after):
    table = drop_tables_after("raw.test_health_empty")
    with db_conn.cursor() as cur:
        cur.execute(f"CREATE TABLE {table} (id int)")
    db_conn.commit()

    result = check_table_has_rows(table)

    assert not result.ok


def test_check_table_exists_true_when_empty(db_conn, drop_tables_after):
    # The whole point of check_table_exists vs. check_table_has_rows: 0 rows
    # is a valid healthy state for a sparse/event-driven table (e.g.
    # raw.mlb_live_game when nothing is currently live) — must not be
    # reported as unhealthy just because it happens to be empty right now.
    table = drop_tables_after("raw.test_health_sparse")
    with db_conn.cursor() as cur:
        cur.execute(f"CREATE TABLE {table} (id int)")
    db_conn.commit()

    result = check_table_exists(table)

    assert result.ok
    assert "0 rows" in result.detail


def test_check_table_exists_false_when_table_never_created():
    result = check_table_exists("raw.test_health_sparse_never_created")

    assert not result.ok
    assert "never bootstrapped" in result.detail


def test_check_last_run_false_when_never_run():
    result = check_last_run(f"test_never_{uuid.uuid4().hex}")
    assert not result.ok
    assert "never run" in result.detail


def test_check_last_run_reports_actionable_message_when_meta_schema_missing(monkeypatch):
    # Same class of regression as test_check_table_has_rows_false_when_table_never_created,
    # but for meta.ingestion_run specifically: a fresh, unmigrated database
    # must not crash this with UndefinedTable. Needs a genuinely separate
    # database (not mlb_test, which every other test assumes is migrated).
    db_name = f"mlb_health_freshtest_{uuid.uuid4().hex[:8]}"
    with psycopg.connect("postgresql:///postgres", autocommit=True) as admin_conn:
        with admin_conn.cursor() as cur:
            cur.execute(f"CREATE DATABASE {db_name}")
        try:
            monkeypatch.setenv("DATABASE_URL", f"postgresql:///{db_name}")
            result = check_last_run("anything")
        finally:
            with admin_conn.cursor() as cur:
                cur.execute(f"DROP DATABASE {db_name}")

    assert not result.ok
    assert "mlb migrate" in result.detail


def test_check_last_run_true_on_success(db_conn):
    source = f"test_health_run_{uuid.uuid4().hex}"
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO meta.ingestion_run (source, mode, status, finished_at) "
            "VALUES (%s, 'bootstrap', 'success', now())",
            (source,),
        )
    db_conn.commit()

    result = check_last_run(source)

    assert result.ok


def test_check_recent_run_false_when_never_run():
    result = check_recent_run(f"test_never_{uuid.uuid4().hex}", max_age_minutes=15)
    assert not result.ok
    assert "never run" in result.detail


def test_check_recent_run_reports_actionable_message_when_meta_schema_missing(monkeypatch):
    db_name = f"mlb_health_freshtest_{uuid.uuid4().hex[:8]}"
    with psycopg.connect("postgresql:///postgres", autocommit=True) as admin_conn:
        with admin_conn.cursor() as cur:
            cur.execute(f"CREATE DATABASE {db_name}")
        try:
            monkeypatch.setenv("DATABASE_URL", f"postgresql:///{db_name}")
            result = check_recent_run("anything", max_age_minutes=15)
        finally:
            with admin_conn.cursor() as cur:
                cur.execute(f"DROP DATABASE {db_name}")

    assert not result.ok
    assert "mlb migrate" in result.detail


def test_check_recent_run_true_when_recent_and_successful(db_conn):
    source = f"test_health_fresh_{uuid.uuid4().hex}"
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO meta.ingestion_run (source, mode, status, started_at, finished_at) "
            "VALUES (%s, 'update', 'success', now() - interval '2 minutes', now())",
            (source,),
        )
    db_conn.commit()

    result = check_recent_run(source, max_age_minutes=15)

    assert result.ok


def test_check_recent_run_false_when_last_run_is_stale(db_conn):
    # The whole point of this check over check_last_run: a scheduled job
    # that silently stopped running (crashed host, disabled crontab entry)
    # still has an old "success" row forever — that must not read as healthy.
    source = f"test_health_stale_{uuid.uuid4().hex}"
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO meta.ingestion_run (source, mode, status, started_at, finished_at) "
            "VALUES (%s, 'update', 'success', now() - interval '45 minutes', now())",
            (source,),
        )
    db_conn.commit()

    result = check_recent_run(source, max_age_minutes=15)

    assert not result.ok
    assert "still running" in result.detail


def test_check_recent_run_false_when_last_run_failed_even_if_recent(db_conn):
    source = f"test_health_failed_{uuid.uuid4().hex}"
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO meta.ingestion_run (source, mode, status, started_at, finished_at, error) "
            "VALUES (%s, 'update', 'failed', now() - interval '1 minute', now(), 'boom')",
            (source,),
        )
    db_conn.commit()

    result = check_recent_run(source, max_age_minutes=15)

    assert not result.ok
    assert "failed" in result.detail
