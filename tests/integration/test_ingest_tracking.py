import uuid

import pytest

from mlb_baseball.ingest import track_run


def _fetch_run(db_conn, source):
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT status, rows, error, finished_at FROM meta.ingestion_run "
            "WHERE source = %s ORDER BY id DESC LIMIT 1",
            (source,),
        )
        return cur.fetchone()


def test_success_path_logs_row_count(db_conn):
    source = f"test_success_{uuid.uuid4().hex}"

    with track_run(db_conn, source, "bootstrap") as result:
        result["rows"] = 42

    status, rows, error, finished_at = _fetch_run(db_conn, source)
    assert status == "success"
    assert rows == 42
    assert error is None
    assert finished_at is not None


def test_failure_path_logs_error_and_leaves_connection_usable(db_conn):
    source = f"test_failure_{uuid.uuid4().hex}"

    with pytest.raises(RuntimeError, match="boom"):
        with track_run(db_conn, source, "bootstrap"):
            raise RuntimeError("boom")

    # Regression test: track_run used to try logging the failure without
    # rolling back the aborted transaction first, which raised a second,
    # more confusing error (InFailedSqlTransaction) that masked the real one.
    status, rows, error, finished_at = _fetch_run(db_conn, source)
    assert status == "failed"
    assert rows is None
    assert "boom" in error
    assert finished_at is not None

    with db_conn.cursor() as cur:
        cur.execute("SELECT 1")
        assert cur.fetchone() == (1,)
