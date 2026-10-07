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
        cur.execute("SELECT count(*) FROM pg_stat_user_tables WHERE schemaname = 'raw'")
        tables_before = cur.fetchone()[0]
    record(db_conn, [Finding("zz_test", "c", "new")])
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM pg_stat_user_tables WHERE schemaname = 'raw'")
        assert cur.fetchone()[0] == tables_before
    _clean(db_conn)
