import uuid

import psycopg

from mlb_baseball import inventory


def test_tables_reports_row_counts(db_conn, drop_tables_after):
    table = drop_tables_after("raw.test_inventory_widgets")
    with db_conn.cursor() as cur:
        cur.execute(f"CREATE TABLE {table} (id int)")
        cur.execute(f"INSERT INTO {table} VALUES (1), (2), (3)")
    db_conn.commit()

    rows = inventory.tables()

    match = next(r for r in rows if r["schema"] == "raw" and r["table"] == "test_inventory_widgets")
    assert match["rows"] == 3


def test_last_runs_reports_most_recent_per_source(db_conn):
    source = f"test_inventory_{uuid.uuid4().hex}"
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO meta.ingestion_run (source, mode, status, rows, finished_at) "
            "VALUES (%s, 'bootstrap', 'success', 10, now())",
            (source,),
        )
        cur.execute(
            "INSERT INTO meta.ingestion_run (source, mode, status, rows, finished_at) "
            "VALUES (%s, 'update', 'success', 2, now())",
            (source,),
        )
    db_conn.commit()

    runs = inventory.last_runs()

    match = next(r for r in runs if r["source"] == source)
    assert match["mode"] == "update"  # the most recent of the two inserted
    assert match["rows"] == 2


def test_last_runs_empty_not_crashing_on_unmigrated_db(monkeypatch):
    # Regression: `mlb inventory` used to crash with a raw UndefinedTable
    # traceback on a fresh, unmigrated database (meta.ingestion_run doesn't
    # exist yet) instead of reporting "nothing to show" — same class of bug
    # as doctor.py's, fixed the same way. Needs a genuinely separate
    # database, not mlb_test (every other test here assumes it's migrated).
    db_name = f"mlb_inventory_freshtest_{uuid.uuid4().hex[:8]}"
    with psycopg.connect("postgresql:///postgres", autocommit=True) as admin_conn:
        with admin_conn.cursor() as cur:
            cur.execute(f"CREATE DATABASE {db_name}")
        try:
            monkeypatch.setenv("DATABASE_URL", f"postgresql:///{db_name}")
            runs = inventory.last_runs()
        finally:
            with admin_conn.cursor() as cur:
                cur.execute(f"DROP DATABASE {db_name}")

    assert runs == []
