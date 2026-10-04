"""The `mlb runs` query against real `meta.ingestion_run` rows."""

import uuid

from mlb_baseball import runs


def _insert(cur, source, mode, status, started="now()", finished="now()", attempt=1):
    cur.execute(
        "INSERT INTO meta.ingestion_run (source, mode, status, attempt, started_at, finished_at)"
        f" VALUES (%s, %s, %s, %s, {started}, {finished})",
        (source, mode, status, attempt),
    )


def test_latest_row_and_latest_success_per_job(db_conn, monkeypatch):
    tag = uuid.uuid4().hex[:8]
    ok_source, flaky, old, manual = (f"{p}_{tag}" for p in ("ok", "flaky", "old", "manual"))
    with db_conn.cursor() as cur:
        _insert(cur, ok_source, "update", "success", "now() - interval '1 hour'")
        _insert(cur, flaky, "nightly", "success", "now() - interval '30 hours'")
        _insert(cur, flaky, "nightly", "failed", "now() - interval '2 hours'", attempt=2)
        _insert(cur, old, "update", "success", "now() - interval '40 days'")
        _insert(cur, manual, "backfill", "success")
    db_conn.commit()

    monkeypatch.setattr(runs, "get_connection", lambda: db_conn)
    by_job = {r.source: r for r in runs.fetch_runs() if r.source.endswith(tag)}

    assert set(by_job) == {ok_source, flaky}  # 40-day-old and backfill jobs are excluded
    assert by_job[ok_source].status == "success"
    assert by_job[flaky].status == "failed" and by_job[flaky].attempt == 2
    assert by_job[flaky].success_at is not None  # earlier success is still known
