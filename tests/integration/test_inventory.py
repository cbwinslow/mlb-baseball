import uuid

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
    assert match["exact"] is True


def test_fast_inventory_hides_partition_children_and_keeps_parents():
    rows = inventory.tables(partitions=False, exact=False)
    names = {f"{row['schema']}.{row['table']}" for row in rows}

    assert "core.play" in names
    assert "core.pitch" in names
    assert "core.play_2025" not in names
    assert "core.pitch_2025" not in names
    assert all(row["exact"] is False for row in rows)


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


def test_last_runs_empty_not_crashing_on_unmigrated_db(monkeypatch, unmigrated_db_connection):
    # Regression: `mlb inventory` used to crash with a raw UndefinedTable
    # traceback on a fresh, unmigrated database (meta.ingestion_run doesn't
    # exist yet) instead of reporting "nothing to show". Simulate the real
    # PostgreSQL exception rather than creating another database.
    monkeypatch.setattr(inventory, "get_connection", lambda: unmigrated_db_connection)
    runs = inventory.last_runs()

    assert runs == []
    assert unmigrated_db_connection.rolled_back
