"""`record` stores the latest schema-watch result per dataset in meta.schema_finding,
and running it twice leaves one row per dataset."""

from mlb_baseball.schema_watch import Drift, Finding, record


def _rows(db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT source, dataset, status, added, error FROM meta.schema_finding "
            "WHERE source = 'zz_test' ORDER BY dataset"
        )
        return cur.fetchall()


def _clean(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM meta.schema_finding WHERE source = 'zz_test'")
    db_conn.commit()


def test_record_is_idempotent_and_keeps_the_latest(db_conn):
    _clean(db_conn)
    findings = [
        Finding("zz_test", "a", "drift", Drift(added={"x": "int"})),
        Finding("zz_test", "b", "unchecked", error="down"),
    ]
    record(db_conn, findings)
    record(db_conn, findings)
    assert _rows(db_conn) == [
        ("zz_test", "a", "drift", {"x": "int"}, ""),
        ("zz_test", "b", "unchecked", {}, "down"),
    ]
    record(db_conn, [Finding("zz_test", "a", "unchanged")])
    assert _rows(db_conn)[0][2:4] == ("unchanged", {})
    _clean(db_conn)


def test_record_writes_nothing_to_raw(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("CREATE TABLE raw.zz_watch_probe (x text)")
        cur.execute("INSERT INTO raw.zz_watch_probe VALUES ('a')")
    db_conn.commit()
    try:
        record(db_conn, [Finding("zz_test", "c", "new")])
        with db_conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM raw.zz_watch_probe")
            assert cur.fetchone()[0] == 1
    finally:
        with db_conn.cursor() as cur:
            cur.execute("DROP TABLE raw.zz_watch_probe")
        db_conn.commit()
        _clean(db_conn)


def test_an_unchecked_run_does_not_erase_a_standing_drift(db_conn):
    _clean(db_conn)
    record(db_conn, [Finding("zz_test", "a", "drift", Drift(added={"x": "int"}))])
    record(db_conn, [Finding("zz_test", "a", "unchecked", error="down")])
    assert _rows(db_conn)[0][2] == "drift"
    record(db_conn, [Finding("zz_test", "a", "unchanged")])
    assert _rows(db_conn)[0][2] == "unchanged"
    _clean(db_conn)
