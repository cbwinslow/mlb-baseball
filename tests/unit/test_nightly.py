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
        "schema-watch --tolerate-unchecked",
        "repair --apply",
        "coverage --unexplained --missing-only --fail-on-gap --light",
    ]
    assert harness.alerts == []
    assert [r[0] for r in harness.records] == [
        "migrate",
        "update",
        "conform",
        "report",
        "predict",
        "populated",
        "schema-watch",
        "repair",
        "coverage",
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


def test_run_child_kills_a_hung_step_and_reports_the_timeout():
    code, tail = nightly.run_child(
        (sys.executable,), ["-c", "import time; time.sleep(60)"], timeout=0.5
    )

    assert code < 0
    assert "step timeout" in tail[-1]


def test_run_child_leaves_a_step_that_finishes_in_time_alone():
    code, tail = nightly.run_child((sys.executable,), ["-c", "print('ok')"], timeout=30)

    assert code == 0
    assert tail == ["ok"]


def test_repair_runs_uses_its_own_short_timeout_and_logs_a_failure(monkeypatch, capsys):
    seen = {}

    def fake_run_child(command, args, env=None, timeout=nightly.STEP_TIMEOUT_SECONDS):
        seen["args"], seen["timeout"] = list(args), timeout
        return 9, ["boom"]

    monkeypatch.setattr(nightly, "run_child", fake_run_child)

    nightly.Nightly(sources=[], retry_pauses=())._repair_runs()

    assert seen == {"args": ["repair-runs"], "timeout": nightly.REPAIR_TIMEOUT_SECONDS}
    assert "repair-runs failed (rc=9): boom" in capsys.readouterr().out


def test_nightly_command_passes_the_pause_and_exits_with_the_result(monkeypatch):
    from mlb_baseball import cli

    built = {}

    class FakeNightly:
        def __init__(self, *, retry_pauses):
            built["retry_pauses"] = retry_pauses

        def run(self):
            return 7

    monkeypatch.setattr(nightly, "Nightly", FakeNightly)

    with pytest.raises(SystemExit) as exit_info:
        cli.main(["nightly", "--pause", "0"])

    assert built["retry_pauses"] == [0.0]
    assert exit_info.value.code == 7


def test_drift_and_gap_steps_fail_the_run_but_do_not_stop_each_other(harness):
    runner, calls = harness("schema-watch")
    assert runner.run() == 1
    assert "repair --apply" in calls()
    assert len(harness.alerts) == 1 and "schema-watch" in harness.alerts[0]


def test_repair_runs_before_the_coverage_check_so_the_check_sees_the_repaired_state(harness):
    runner, calls = harness()
    runner.run()
    order = calls()
    assert order.index("repair --apply") < order.index(
        "coverage --unexplained --missing-only --fail-on-gap --light"
    )


def test_a_failed_repair_fails_the_run_and_alerts(harness):
    runner, calls = harness("repair")
    assert runner.run() == 1
    assert any("repair" in a for a in harness.alerts)
