"""`scripts/mlb_daily_update.sh` must run migrate -> update -> conform ->
report -> predict -> populated-check as *independently tracked* steps (spec
2026-08-28, Phase 0; pipeline-freshness, 2026-09-27): a partial failure in one
step still attempts the next, each step is timestamped and logged separately,
and `update` skips `mlb_api` (kept fresh by the separate 5-minute cron whose
lock the daily run would otherwise fight). Two gates: a failed `migrate` stops
every later step, and `report` runs only when `conform` succeeded.

Driven through the real script with a stub `mlb` on PATH -- an argparse
argument silently dropped, or a `set -e` reintroduced, would break the
production pipeline with nothing else to catch it.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "mlb_daily_update.sh"


def _run(tmp_path: Path, *, fail_step: str | None = None) -> tuple[int, str, str]:
    """Run the script with a stub `mlb` that records its args and, for
    `fail_step`, exits non-zero. Returns (rc, calls-log, daily-log)."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    calls_log = tmp_path / "calls.log"
    stub = bindir / "mlb"
    stub.write_text(
        "#!/usr/bin/env bash\n"
        f'echo "$@" >> "{calls_log}"\n'
        f'if [ "$1" = "{fail_step or "__none__"}" ]; then exit 3; fi\n'
        "exit 0\n"
    )
    stub.chmod(0o755)

    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    (repo / ".venv" / "bin").mkdir(parents=True)
    (repo / ".venv" / "bin" / "mlb").symlink_to(stub)
    (repo / "scripts" / "mlb_daily_update.sh").write_text(SCRIPT.read_text())
    (repo / "scripts" / "mlb_daily_update.sh").chmod(0o755)

    env = dict(
        os.environ,
        PATH=f"{bindir}:{os.environ['PATH']}",
        # Per-run lock/log so concurrent test invocations (xdist, a second
        # checkout) never take the "already running, skipping" branch.
        MLB_DAILY_LOCK_FILE=str(tmp_path / "daily.lock"),
        MLB_DAILY_LOG_FILE=str(tmp_path / "daily.log"),
    )
    proc = subprocess.run(
        ["bash", str(repo / "scripts" / "mlb_daily_update.sh")],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    daily_log = (tmp_path / "daily.log").read_text()
    return proc.returncode, calls_log.read_text() if calls_log.exists() else "", daily_log


_FULL_RUN = [
    "repair-runs",
    "migrate",
    "update --skip mlb_api",
    "conform",
    "report",
    "predict",
    "doctor --populated",
]


def test_runs_every_step_in_order_and_skips_mlb_api(tmp_path):
    rc, calls, _ = _run(tmp_path)
    assert rc == 0
    # repair-runs clears crashed 'running' rows before the pipeline (issue #180);
    # it precedes the tracked steps and its exit code is ignored.
    assert calls.strip().splitlines() == _FULL_RUN


def test_repair_runs_failure_does_not_stop_the_pipeline(tmp_path):
    rc, calls, _ = _run(tmp_path, fail_step="repair-runs")
    # repair-runs failed, but every tracked step still ran and rc is 0
    # (its `|| true` swallows the failure; it is not a tracked step).
    assert rc == 0
    assert calls.strip().splitlines() == _FULL_RUN


def test_a_failing_step_does_not_skip_the_independent_later_steps(tmp_path):
    rc, calls, log = _run(tmp_path, fail_step="predict")
    # predict failed, but the populated check was still attempted...
    assert "doctor --populated" in calls
    # ...and the overall exit code reflects the failure.
    assert rc != 0
    assert "step predict: FAILED rc=3" in log
    assert "step populated: starting" in log


def test_a_failed_migrate_stops_every_later_step(tmp_path):
    rc, calls, log = _run(tmp_path, fail_step="migrate")
    # Later steps would run against the old schema (the 2026-09-24 conform crash).
    assert calls.strip().splitlines() == ["repair-runs", "migrate"]
    assert rc != 0
    assert "step migrate: FAILED rc=3" in log
    assert "step update: starting" not in log


def test_report_is_skipped_when_conform_fails(tmp_path):
    rc, calls, log = _run(tmp_path, fail_step="conform")
    lines = calls.strip().splitlines()
    assert "report" not in lines
    # the independent steps still run, and the run fails
    assert "predict" in lines
    assert "doctor --populated" in lines
    assert rc != 0
    assert "step conform: FAILED rc=3" in log
    assert "conform failed; skipping report" in log


def test_report_failure_is_reported_and_populated_check_still_runs(tmp_path):
    rc, calls, log = _run(tmp_path, fail_step="report")
    assert "doctor --populated" in calls
    assert rc != 0
    assert "step report: FAILED rc=3" in log


def test_an_empty_backbone_makes_the_run_exit_non_zero(tmp_path):
    # `doctor --populated` exits 1 when a relation is empty; the stub uses rc 3
    # for the failing step, and the script must surface it either way.
    rc, _, log = _run(tmp_path, fail_step="doctor")
    assert rc != 0
    assert "step populated: FAILED" in log


def test_each_step_is_timestamped_and_timed_separately(tmp_path):
    _, _, log = _run(tmp_path)
    for step in ("migrate", "update", "conform", "report", "predict", "populated"):
        assert f"step {step}: starting" in log
        assert f"step {step}: ok" in log
    # duration recorded for every step (pipeline-freshness 2.1)
    assert log.count("took ") == 6
