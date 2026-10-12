"""`mlb nightly`: pipeline failures vs data-health findings, and the run marker
that lets an outside check notice a run that died. A fake child process stands in
for `mlb <step>`; every database touch is stubbed, so this never reaches PostgreSQL
(the update-retry tests against real rows live in tests/integration)."""

import json
import sys
from datetime import UTC, datetime, timedelta

import pytest

from mlb_baseball import nightly

CHILD = """\
import os, sys
sys.exit(1 if sys.argv[1] in os.environ.get("FAIL_STEPS", "").split(",") else 0)
"""


@pytest.fixture
def run_nightly(tmp_path, monkeypatch):
    script = tmp_path / "child.py"
    script.write_text(CHILD)
    monkeypatch.setattr(nightly, "record_step", lambda *a, **k: None)
    monkeypatch.setattr(nightly, "sources_without_success", lambda *a, **k: [])
    monkeypatch.setattr(nightly, "snapshot_query_stats", lambda: None)
    monkeypatch.setattr(nightly, "prune_monitor", lambda: True)

    def go(fail: str = ""):
        monkeypatch.setenv("FAIL_STEPS", fail)
        alerts: list[str] = []
        marker = tmp_path / "nightly_run.json"
        runner = nightly.Nightly(
            command=(sys.executable, str(script)),
            sources=["a"],
            retry_pauses=(),
            notify=alerts.append,
            sleep=lambda s: None,
            marker_path=marker,
        )
        return runner.run(), alerts, marker

    return go


def test_clean_run_exits_zero_and_sends_nothing(run_nightly):
    rc, alerts, _ = run_nightly()
    assert rc == 0
    assert alerts == []


def test_pipeline_step_failure_exits_one_and_alerts_at_once(run_nightly):
    rc, alerts, _ = run_nightly("conform")
    assert rc == 1
    assert len(alerts) == 1
    assert "step conform failed" in alerts[0]


@pytest.mark.parametrize("step", ["doctor", "coverage", "schema-watch", "repair"])
def test_health_finding_does_not_change_exit_code(run_nightly, step):
    rc, alerts, _ = run_nightly(step)
    assert rc == 0
    assert len(alerts) == 1  # one digest, not a failure alert
    assert "health digest" in alerts[0]


def test_several_health_findings_make_one_digest(run_nightly):
    rc, alerts, _ = run_nightly("coverage,schema-watch")
    assert rc == 0
    assert len(alerts) == 1
    assert "coverage" in alerts[0] and "schema-watch" in alerts[0]


def test_pipeline_failure_and_health_finding_are_reported_separately(run_nightly):
    rc, alerts, _ = run_nightly("predict,coverage")
    assert rc == 1
    assert len(alerts) == 2
    assert any("step predict failed" in a for a in alerts)
    assert any("health digest" in a and "coverage" in a for a in alerts)


def test_marker_records_start_then_finish_and_exit_code(run_nightly):
    rc, _, marker = run_nightly("conform")
    data = json.loads(marker.read_text())
    assert data["rc"] == rc == 1
    assert data["finished_at"] is not None
    assert data["started_at"] <= data["finished_at"]


NOW = datetime(2026, 10, 12, 11, 0, tzinfo=UTC)


def _write(path, started, finished=None, rc=None):
    path.write_text(
        json.dumps(
            {
                "started_at": started.isoformat(),
                "finished_at": finished.isoformat() if finished else None,
                "rc": rc,
            }
        )
    )


def test_check_flags_a_run_that_never_finished(tmp_path):
    marker = tmp_path / "m.json"
    _write(marker, NOW - timedelta(hours=6))
    message = nightly.check_marker(marker, NOW)
    assert message is not None and "did not finish" in message


def test_check_allows_a_run_still_inside_its_window(tmp_path):
    marker = tmp_path / "m.json"
    _write(marker, NOW - timedelta(hours=3))
    assert nightly.check_marker(marker, NOW) is None


def test_check_flags_a_night_that_never_started(tmp_path):
    marker = tmp_path / "m.json"
    _write(marker, NOW - timedelta(hours=30), NOW - timedelta(hours=27), 0)
    message = nightly.check_marker(marker, NOW)
    assert message is not None and "did not start" in message


def test_check_is_quiet_after_a_finished_run_even_if_it_failed(tmp_path):
    marker = tmp_path / "m.json"
    _write(marker, NOW - timedelta(hours=5), NOW - timedelta(hours=1), 1)
    assert nightly.check_marker(marker, NOW) is None  # the failing step already alerted


def test_check_flags_a_missing_marker(tmp_path):
    message = nightly.check_marker(tmp_path / "absent.json", NOW)
    assert message is not None and "no nightly run record" in message


def test_check_flags_an_unreadable_marker(tmp_path):
    marker = tmp_path / "m.json"
    marker.write_text("{not json")
    message = nightly.check_marker(marker, NOW)
    assert message is not None and "unreadable" in message


@pytest.fixture
def cli_marker(tmp_path, monkeypatch):
    from mlb_baseball import alert

    sent: list[str] = []
    monkeypatch.setattr(alert, "alert", lambda message: sent.append(message) or True)
    monkeypatch.setenv("MLB_HOME", str(tmp_path))
    return tmp_path / "nightly_run.json", sent


def test_check_flag_through_the_real_parser_alerts_on_a_dead_run(cli_marker):
    from mlb_baseball import cli

    marker, sent = cli_marker
    _write(marker, datetime.now(UTC) - timedelta(hours=8))
    with pytest.raises(SystemExit) as exc:
        cli.main(["nightly", "--check"])
    assert exc.value.code == 1
    assert len(sent) == 1 and "did not finish" in sent[0]


def test_check_flag_through_the_real_parser_is_quiet_when_healthy(cli_marker, capsys):
    from mlb_baseball import cli

    marker, sent = cli_marker
    now = datetime.now(UTC)
    _write(marker, now - timedelta(hours=3), now - timedelta(hours=1), 0)
    with pytest.raises(SystemExit) as exc:
        cli.main(["nightly", "--check"])
    assert exc.value.code == 0
    assert sent == []
    assert "ok" in capsys.readouterr().out
