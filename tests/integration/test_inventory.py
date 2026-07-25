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
