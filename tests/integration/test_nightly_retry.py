"""`mlb nightly` update retries against real PostgreSQL rows: only sources
without a success tonight are rerun, each attempt is one `nightly` row, and an
exhausted source alerts once. A fake child process stands in for `mlb update`;
it records runs with the real `track_run`, exactly as connectors do."""

import sys
import uuid

import pytest

from mlb_baseball import nightly

CHILD = """\
import os, sys
from mlb_baseball.db import get_connection
from mlb_baseball.ingest import track_run

args = sys.argv[1:]
open(os.environ["CALLS"], "a").write(" ".join(args) + "\\n")
if args[0] != "update":
    sys.exit(0)
skip = {args[i + 1] for i, a in enumerate(args) if a == "--skip"}
attempt = int(os.environ["MLB_RUN_ATTEMPT"])
failed = False
with get_connection() as conn:
    for source in os.environ["SOURCES"].split(","):
        if source in skip:
            continue
        try:
            with track_run(conn, source, "update") as result:
                if source == os.environ["FLAKY"] and attempt < int(os.environ["OK_ON"]):
                    raise RuntimeError("503 from server")
                result["rows"] = 1
        except RuntimeError:
            failed = True
sys.exit(1 if failed else 0)
"""


@pytest.fixture
def run_update(tmp_path, monkeypatch, db_conn):
    script = tmp_path / "child.py"
    script.write_text(CHILD)
    calls = tmp_path / "calls.log"
    monkeypatch.setenv("CALLS", str(calls))
    tag = uuid.uuid4().hex[:8]
    good, flaky = f"good_{tag}", f"flaky_{tag}"
    monkeypatch.setenv("SOURCES", f"{good},{flaky}")
    monkeypatch.setenv("FLAKY", flaky)
    alerts: list[str] = []

    def go(ok_on: int):
        monkeypatch.setenv("OK_ON", str(ok_on))
        runner = nightly.Nightly(
            command=(sys.executable, str(script)),
            sources=[good, flaky],
            retry_pauses=(0, 0),
            notify=alerts.append,
            sleep=lambda s: None,
        )
        ok = runner.update()
        with db_conn.cursor() as cur:
            cur.execute(
                "SELECT source, status, attempt FROM meta.ingestion_run "
                "WHERE source IN (%s, %s) ORDER BY id",
                (good, flaky),
            )
            rows = cur.fetchall()
            cur.execute(
                "SELECT attempt, status FROM meta.ingestion_run "
                "WHERE source = 'update' AND mode = 'nightly' "
                "AND started_at > now() - interval '1 minute' "
                "ORDER BY id"
            )
            steps = cur.fetchall()
        return (
            ok,
            rows,
            steps,
            [c for c in calls.read_text().splitlines() if c.startswith("update")],
        )

    go.alerts, go.names = alerts, (good, flaky)
    return go


def test_source_that_fails_once_is_retried_alone_without_duplicates(run_update):
    good, flaky = run_update.names
    ok, rows, steps, calls = run_update(ok_on=2)

    assert ok is True
    assert rows == [
        (good, "success", 1),
        (flaky, "failed", 1),
        (flaky, "success", 2),
    ]  # the good source ran once; one success row per source
    assert calls[0] == "update --skip mlb_api"
    assert f"--skip {good}" in calls[1]  # retry only reruns the failed source
    assert steps[-2:] == [(1, "failed"), (2, "success")]
    assert run_update.alerts == []


def test_exhausted_retries_alert_exactly_once(run_update):
    good, flaky = run_update.names
    ok, rows, steps, calls = run_update(ok_on=99)

    assert ok is False
    assert [r for r in rows if r[0] == flaky] == [
        (flaky, "failed", 1),
        (flaky, "failed", 2),
        (flaky, "failed", 3),
    ]
    assert len(run_update.alerts) == 1
    assert flaky in run_update.alerts[0] and "3 attempts" in run_update.alerts[0]
