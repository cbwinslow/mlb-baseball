import os
import uuid

import psycopg
import pytest

from mlb_baseball.ingest import reap_stale_runs, track_run


def _fetch_run(db_conn, source):
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT status, rows, error, finished_at FROM meta.ingestion_run "
            "WHERE source = %s ORDER BY id DESC LIMIT 1",
            (source,),
        )
        return cur.fetchone()


def _insert_running(db_conn, source, pid):
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO meta.ingestion_run (source, mode, status, pid) "
            "VALUES (%s, 'bootstrap', 'running', %s) RETURNING id",
            (source, pid),
        )
        run_id = cur.fetchone()[0]
    db_conn.commit()
    return run_id


def _fetch_status(db_conn, run_id):
    with db_conn.cursor() as cur:
        cur.execute("SELECT status, error FROM meta.ingestion_run WHERE id = %s", (run_id,))
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


def test_track_run_stores_the_running_process_pid(db_conn):
    source = f"test_pid_{uuid.uuid4().hex}"

    with track_run(db_conn, source, "bootstrap") as result:
        result["rows"] = 1

    with db_conn.cursor() as cur:
        cur.execute("SELECT pid FROM meta.ingestion_run WHERE source = %s", (source,))
        (pid,) = cur.fetchone()
    assert pid == os.getpid()


def test_track_run_rejects_overlapping_runs_for_the_same_source(db_conn):
    source = f"test_overlap_{uuid.uuid4().hex}"

    with psycopg.connect(os.environ["DATABASE_URL"]) as second_conn:
        with track_run(db_conn, source, "bootstrap"):
            with pytest.raises(RuntimeError, match="another ingestion run is already active"):
                with track_run(second_conn, source, "bootstrap"):
                    pass

        with track_run(second_conn, source, "bootstrap") as result:
            result["rows"] = 1


def test_workflow_lock_serializes_connectors_and_derived_stages(db_conn):
    source = f"test_workflow_{uuid.uuid4().hex}"
    with psycopg.connect(os.environ["DATABASE_URL"]) as second_conn:
        with track_run(db_conn, source, "bootstrap"):
            with pytest.raises(RuntimeError, match="another ingestion or derived-data stage"):
                with track_run(second_conn, "model", "features", workflow="exclusive"):
                    pass

        with track_run(db_conn, "model", "features", workflow="exclusive"):
            with pytest.raises(RuntimeError, match="another ingestion or derived-data stage"):
                with track_run(second_conn, source, "bootstrap"):
                    pass


def test_reap_stale_runs_marks_dead_pid_as_failed(db_conn):
    source = f"test_reap_dead_{uuid.uuid4().hex}"
    # PID 1 is init/systemd on any real Linux host, never this test process —
    # but a PID guaranteed to be dead needs to not collide with a live one.
    # Use a PID far outside the kernel's normal allocation range instead.
    dead_pid = 2**22
    run_id = _insert_running(db_conn, source, dead_pid)

    reaped = reap_stale_runs(db_conn)

    reaped_ids = {r["id"] for r in reaped}
    assert run_id in reaped_ids
    status, error = _fetch_status(db_conn, run_id)
    assert status == "failed"
    assert str(dead_pid) in error


def test_reap_stale_runs_leaves_live_pid_running(db_conn):
    source = f"test_reap_live_{uuid.uuid4().hex}"
    run_id = _insert_running(db_conn, source, os.getpid())

    reaped = reap_stale_runs(db_conn)

    reaped_ids = {r["id"] for r in reaped}
    assert run_id not in reaped_ids
    status, error = _fetch_status(db_conn, run_id)
    assert status == "running"
    assert error is None


def test_reap_stale_runs_leaves_null_pid_rows_alone(db_conn):
    source = f"test_reap_null_{uuid.uuid4().hex}"
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO meta.ingestion_run (source, mode, status, pid) "
            "VALUES (%s, 'bootstrap', 'running', NULL) RETURNING id",
            (source,),
        )
        run_id = cur.fetchone()[0]
    db_conn.commit()

    reaped = reap_stale_runs(db_conn)

    reaped_ids = {r["id"] for r in reaped}
    assert run_id not in reaped_ids
    status, error = _fetch_status(db_conn, run_id)
    assert status == "running"
    assert error is None
