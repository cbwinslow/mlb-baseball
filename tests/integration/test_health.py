import uuid

from mlb_baseball.health import check_last_run, check_table_has_rows


def test_check_table_has_rows_true_when_populated(db_conn, drop_tables_after):
    table = drop_tables_after("raw.test_health_widgets")
    with db_conn.cursor() as cur:
        cur.execute(f"CREATE TABLE {table} (id int)")
        cur.execute(f"INSERT INTO {table} VALUES (1)")
    db_conn.commit()

    result = check_table_has_rows(table)

    assert result.ok
    assert "1 rows" in result.detail


def test_check_table_has_rows_false_when_empty(db_conn, drop_tables_after):
    table = drop_tables_after("raw.test_health_empty")
    with db_conn.cursor() as cur:
        cur.execute(f"CREATE TABLE {table} (id int)")
    db_conn.commit()

    result = check_table_has_rows(table)

    assert not result.ok


def test_check_last_run_false_when_never_run():
    result = check_last_run(f"test_never_{uuid.uuid4().hex}")
    assert not result.ok
    assert "never run" in result.detail


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
