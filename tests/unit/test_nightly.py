"""`mlb nightly` gates and alerts, driven through real child processes (a fake
`mlb` script) so exit codes and kills are seen exactly as in production. The
database bits are stubbed here; tests/integration/test_nightly_retry.py covers
them against PostgreSQL."""

import sys
from pathlib import Path

import pytest

from mlb_baseball import nightly

FAKE = """\
import os, sys
open(os.environ["CALLS"], "a").write(" ".join(sys.argv[1:]) + "\\n")
if sys.argv[1] in os.environ.get("FAIL", "").split(","):
    sys.exit(3)
"""


@pytest.fixture
def harness(tmp_path, monkeypatch):
    script = tmp_path / "fake_mlb.py"
    script.write_text(FAKE)
    calls = tmp_path / "calls.log"
    monkeypatch.setenv("CALLS", str(calls))
    records: list[tuple] = []
    monkeypatch.setattr(nightly, "record_step", lambda *a: records.append(a))
    monkeypatch.setattr(nightly, "sources_without_success", lambda expected, since: [])
    monkeypatch.setattr(nightly, "snapshot_query_stats", lambda: 0)
    alerts: list[str] = []

    def make(fail: str = "") -> tuple[nightly.Nightly, "callable"]:
        monkeypatch.setenv("FAIL", fail)
        runner = nightly.Nightly(
            command=(sys.executable, str(script)),
            sources=["a", "b"],
            notify=alerts.append,
            sleep=lambda s: None,
        )
        return runner, lambda: Path(calls).read_text().splitlines() if calls.exists() else []

    make.alerts = alerts
    make.records = records
    return make


def test_full_run_order_and_skips_mlb_api(harness):
    runner, calls = harness()
    assert runner.run() == 0
    assert calls() == [
        "repair-runs",
        "migrate",
        "update --skip mlb_api",
        "repair-runs",
        "conform",
        "report",
        "predict",
        "doctor --populated",
    ]
    assert harness.alerts == []
    assert [r[0] for r in harness.records] == [
        "migrate",
        "update",
        "conform",
        "report",
        "predict",
        "populated",
    ]


def test_migrate_failure_stops_everything_and_alerts_once(harness):
    runner, calls = harness("migrate")
    assert runner.run() == 1
    assert calls() == ["repair-runs", "migrate"]
    assert len(harness.alerts) == 1 and "migrate" in harness.alerts[0]


def test_conform_failure_skips_report_but_still_predicts(harness):
    runner, calls = harness("conform")
    assert runner.run() == 1
    assert "report" not in calls() and "predict" in calls()
    assert len(harness.alerts) == 1 and "conform" in harness.alerts[0]


def test_code_bound_steps_are_not_retried(harness):
    runner, calls = harness("predict")
    runner.run()
    assert calls().count("predict") == 1


def test_a_killed_child_counts_as_a_failure(harness, tmp_path, monkeypatch):
    killer = tmp_path / "killer.py"
    killer.write_text("import os, signal\nos.kill(os.getpid(), signal.SIGKILL)\n")
    runner = nightly.Nightly(
        command=(sys.executable, str(killer)), sources=["a"], notify=harness.alerts.append
    )
    assert runner.step("conform", ["conform"]) is False
    assert "rc=-9" in harness.alerts[0]


def test_no_alert_hook_means_log_only(harness, monkeypatch, tmp_path, caplog):
    # The real alert() with nothing configured must not raise or change the exit code.
    monkeypatch.delenv("MLB_ALERT_COMMAND", raising=False)
    monkeypatch.delenv("MLB_CONFIG", raising=False)
    monkeypatch.chdir(tmp_path)
    runner, _ = harness("conform")
    runner.notify = nightly.alert
    assert runner.run() == 1
