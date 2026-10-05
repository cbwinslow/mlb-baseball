"""Run monitor: SQL functions, the item-history trigger, the prune procedure,
and the Python helper (mlb_baseball.opsmon). Real PostgreSQL throughout: the
behaviour under test is the database's own (triggers, function throttling)."""

from __future__ import annotations

import time
import uuid

import pytest

from mlb_baseball import opsmon
from mlb_baseball.ingest import record_items, track_run


def _one(db_conn, sql, params=()):
    with db_conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()


def _new_run(db_conn, source=None, planned=None):
    source = source or f"ops_{uuid.uuid4().hex}"
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO meta.ingestion_run (source, mode, status, pid, items_planned) "
            "VALUES (%s, 'backfill', 'running', 1, %s) RETURNING id",
            (source, planned),
        )
        run_id = cur.fetchone()[0]
    db_conn.commit()
    return run_id


@pytest.fixture(autouse=True)
def _clean(db_conn):
    yield
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM meta.op_span WHERE op LIKE 'test.%'")
        cur.execute("DELETE FROM meta.ingestion_item_history WHERE source LIKE 'ops_%'")
        cur.execute("DELETE FROM meta.ingestion_item WHERE source LIKE 'ops_%'")
        cur.execute("DELETE FROM meta.ingestion_run WHERE source LIKE 'ops_%'")
    db_conn.commit()


# --- meta.run_progress -----------------------------------------------------


def test_run_progress_writes_then_throttles(db_conn):
    run_id = _new_run(db_conn)
    first = _one(db_conn, "SELECT meta.run_progress(%s, 10, 100, 3)", (run_id,))[0]
    second = _one(db_conn, "SELECT meta.run_progress(%s, 20, 100, 6)", (run_id,))[0]
    db_conn.commit()
    assert first is True
    assert second is False  # inside the 30 s throttle window
    done, planned, requests = _one(
        db_conn,
        "SELECT items_done, items_planned, requests FROM meta.ingestion_run WHERE id = %s",
        (run_id,),
    )
    assert (done, planned, requests) == (10, 100, 3)


def test_run_progress_force_bypasses_throttle(db_conn):
    run_id = _new_run(db_conn)
    _one(db_conn, "SELECT meta.run_progress(%s, 10, 100, 3)", (run_id,))
    forced = _one(
        db_conn, "SELECT meta.run_progress(%s, 100, 100, 9, interval '0 seconds')", (run_id,)
    )[0]
    db_conn.commit()
    assert forced is True
    assert _one(db_conn, "SELECT items_done FROM meta.ingestion_run WHERE id = %s", (run_id,)) == (
        100,
    )


# --- meta.stuck_runs / run_health -----------------------------------------


def test_stuck_runs_flags_silent_opted_in_runs_only(db_conn):
    silent = _new_run(db_conn, planned=100)
    quiet_legacy = _new_run(db_conn, planned=None)  # a connector that never reports
    healthy = _new_run(db_conn, planned=100)
    with db_conn.cursor() as cur:
        cur.execute(
            "UPDATE meta.ingestion_run SET last_progress_at = now() - interval '2 hours', "
            "started_at = now() - interval '3 hours' WHERE id = %s",
            (silent,),
        )
        cur.execute(
            "UPDATE meta.ingestion_run SET started_at = now() - interval '3 hours' WHERE id = %s",
            (quiet_legacy,),
        )
        cur.execute(
            "UPDATE meta.ingestion_run SET last_progress_at = now() WHERE id = %s", (healthy,)
        )
    db_conn.commit()
    ids = {
        r[0] for r in _rows(db_conn, "SELECT run_id FROM meta.stuck_runs(interval '15 minutes')")
    }
    assert silent in ids
    assert quiet_legacy not in ids
    assert healthy not in ids


def _rows(db_conn, sql, params=None):
    with db_conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def test_run_health_reports_rate_and_eta(db_conn):
    run_id = _new_run(db_conn, planned=1000)
    with db_conn.cursor() as cur:
        cur.execute(
            "UPDATE meta.ingestion_run SET started_at = now() - interval '100 seconds', "
            "items_done = 250, last_progress_at = now() WHERE id = %s",
            (run_id,),
        )
    db_conn.commit()
    rate, eta = _one(
        db_conn,
        "SELECT items_per_second, eta_seconds FROM meta.run_health WHERE run_id = %s",
        (run_id,),
    )
    assert float(rate) == pytest.approx(2.5, rel=0.1)
    assert float(eta) == pytest.approx(300, rel=0.1)  # 750 left at 2.5/s


# --- item history trigger --------------------------------------------------


def _item(source, key, status, **extra):
    return {"source": source, "dataset": "d", "item_key": key, "status": status, **extra}


def test_item_history_records_failures_and_the_later_success(db_conn):
    source = f"ops_{uuid.uuid4().hex}"
    record_items(db_conn, [_item(source, "k1", "failed", error="HTTP 500", http_status=500)])
    db_conn.commit()
    record_items(db_conn, [_item(source, "k1", "loaded", rows=7)])
    db_conn.commit()
    history = _rows(
        db_conn,
        "SELECT status, error FROM meta.ingestion_item_history WHERE source = %s ORDER BY id",
        (source,),
    )
    assert history == [("failed", "HTTP 500"), ("loaded", None)]
    attempts = _one(
        db_conn, "SELECT attempts FROM meta.ingestion_item WHERE source = %s", (source,)
    )[0]
    assert attempts == 2


def test_item_history_skips_plain_first_time_loads(db_conn):
    source = f"ops_{uuid.uuid4().hex}"
    record_items(db_conn, [_item(source, f"k{i}", "loaded") for i in range(5)])
    db_conn.commit()
    assert _one(
        db_conn, "SELECT count(*) FROM meta.ingestion_item_history WHERE source = %s", (source,)
    ) == (0,)


# --- meta.record_op / prune procedure -------------------------------------


def test_prune_ops_procedure_removes_only_old_rows(db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO meta.op_span (op, started_at, duration_ms, status) VALUES "
            "('test.old', now() - interval '400 days', 5, 'ok'), "
            "('test.new', now(), 5, 'ok')"
        )
    db_conn.commit()
    with db_conn.cursor() as cur:
        cur.execute("CALL meta.prune_ops(interval '180 days')")
    db_conn.commit()
    ops = {r[0] for r in _rows(db_conn, "SELECT op FROM meta.op_span WHERE op LIKE 'test.%'")}
    assert ops == {"test.new"}


# --- mlb_baseball.opsmon ---------------------------------------------------


def test_timed_records_duration_status_and_attrs(db_conn):
    run_id = _new_run(db_conn)
    mon = opsmon.Monitor(run_id=run_id)
    with mon.timed("test.fetch", market="m1") as op:
        time.sleep(0.05)
        op.rows = 12
        op.requests = 2
    mon.close()
    status, ms, rows, requests, attrs, rid = _one(
        db_conn,
        "SELECT status, duration_ms, rows, requests, attrs, run_id FROM meta.op_span "
        "WHERE op = 'test.fetch'",
    )
    assert status == "ok"
    assert ms >= 45
    assert (rows, requests, rid) == (12, 2, run_id)
    assert attrs == {"market": "m1"}


def test_timed_records_failure_and_reraises(db_conn):
    mon = opsmon.Monitor(run_id=None)
    with pytest.raises(RuntimeError):
        with mon.timed("test.boom"):
            raise RuntimeError("source went away")
    mon.close()
    status, error = _one(db_conn, "SELECT status, error FROM meta.op_span WHERE op = 'test.boom'")
    assert status == "failed"
    assert "source went away" in error


def test_monitor_failure_never_breaks_the_caller(db_conn, monkeypatch):
    mon = opsmon.Monitor(run_id=None)

    def broken(*args, **kwargs):
        raise RuntimeError("monitor database unreachable")

    monkeypatch.setattr(mon, "_execute", broken)
    with mon.timed("test.safe") as op:
        op.rows = 1  # the work itself must still run and return
    mon.progress(done=1, planned=2)  # and progress reporting must not raise
    mon.close()


def test_progress_updates_run_row_and_is_throttled_client_side(db_conn):
    run_id = _new_run(db_conn)
    mon = opsmon.Monitor(run_id=run_id, min_interval=3600)
    mon.progress(done=5, planned=50, requests=1)
    mon.progress(done=9, planned=50, requests=2)  # throttled: not written
    mon.close()
    assert _one(
        db_conn,
        "SELECT items_done, items_planned FROM meta.ingestion_run WHERE id = %s",
        (run_id,),
    ) == (5, 50)


def test_progress_final_flush_writes_last_state(db_conn):
    run_id = _new_run(db_conn)
    mon = opsmon.Monitor(run_id=run_id, min_interval=3600)
    mon.progress(done=5, planned=50, requests=1)
    mon.progress(done=50, planned=50, requests=10)
    mon.finish()
    mon.close()
    assert _one(
        db_conn, "SELECT items_done, requests FROM meta.ingestion_run WHERE id = %s", (run_id,)
    ) == (50, 10)


def test_track_run_result_exposes_a_monitor(db_conn):
    source = f"ops_{uuid.uuid4().hex}"
    with track_run(db_conn, source, "backfill", workflow=None) as result:
        mon = opsmon.Monitor(run_id=result["run_id"])
        mon.progress(done=1, planned=2)
        mon.close()
        result["rows"] = 1
    done, planned = _one(
        db_conn,
        "SELECT items_done, items_planned FROM meta.ingestion_run WHERE source = %s",
        (source,),
    )
    assert (done, planned) == (1, 2)


# --- doctor check, record_items duration, nightly prune --------------------


def test_doctor_reports_a_silent_run_with_id_and_last_progress(db_conn):
    from mlb_baseball import doctor

    source = f"ops_{uuid.uuid4().hex}"
    run_id = _new_run(db_conn, source=source, planned=100)
    with db_conn.cursor() as cur:
        cur.execute(
            "UPDATE meta.ingestion_run SET started_at = now() - interval '3 hours', "
            "last_progress_at = now() - interval '2 hours', items_done = 40 WHERE id = %s",
            (run_id,),
        )
    db_conn.commit()
    result = doctor._silent_runs()
    assert not result.ok
    assert source in result.detail
    assert str(run_id) in result.detail
    assert "40/100" in result.detail


def test_doctor_silent_runs_ok_when_nothing_is_silent(db_conn):
    from mlb_baseball import doctor

    with db_conn.cursor() as cur:
        cur.execute(
            "UPDATE meta.ingestion_run SET status = 'failed' "
            "WHERE items_planned IS NOT NULL AND status = 'running'"
        )
    db_conn.commit()
    assert doctor._silent_runs().ok


def test_record_items_stores_the_attempt_duration(db_conn):
    source = f"ops_{uuid.uuid4().hex}"
    record_items(db_conn, [_item(source, "k1", "loaded", duration_ms=1234)])
    db_conn.commit()
    assert _one(
        db_conn, "SELECT duration_ms FROM meta.ingestion_item WHERE source = %s", (source,)
    ) == (1234,)


def test_nightly_prunes_the_monitor_tables(db_conn):
    from mlb_baseball import nightly

    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO meta.op_span (op, started_at, duration_ms, status) "
            "VALUES ('test.stale', now() - interval '999 days', 1, 'ok')"
        )
    db_conn.commit()
    nightly.prune_monitor()
    assert _one(db_conn, "SELECT count(*) FROM meta.op_span WHERE op = 'test.stale'") == (0,)


def test_replace_dataframe_range_clears_only_the_window_of_the_given_keys(db_conn):
    import pandas as pd

    from mlb_baseball.load import ensure_table, replace_dataframe_range

    table = f"raw.ops_range_{uuid.uuid4().hex[:8]}"
    ensure_table(db_conn, table, ["k", "ts", "v"], index_column="k")
    try:
        first = pd.DataFrame({"k": ["a", "a", "b"], "ts": [10, 20, 10], "v": ["1", "2", "3"]})
        replace_dataframe_range(
            db_conn,
            table,
            first,
            key_column="k",
            keys=["a", "b"],
            range_column="ts",
            low=0,
            high=30,
        )
        again = pd.DataFrame({"k": ["a"], "ts": [10], "v": ["9"]})  # window [0, 15) for a only
        replace_dataframe_range(
            db_conn, table, again, key_column="k", keys=["a"], range_column="ts", low=0, high=15
        )
        db_conn.commit()
        rows = _rows(db_conn, f"SELECT k, ts, v FROM {table} ORDER BY k, ts::int")
        assert rows == [("a", "10", "9"), ("a", "20", "2"), ("b", "10", "3")]
    finally:
        db_conn.rollback()
        with db_conn.cursor() as cur:
            cur.execute(f"DROP TABLE IF EXISTS {table}")
        db_conn.commit()
