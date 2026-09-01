"""`scripts/mlb_daily_update.sh` must run update -> conform -> predict as
three *independently tracked* steps (spec 2026-08-28, Phase 0): a partial
failure in one step still attempts the next, each step is timestamped and
logged separately, and `update` skips `mlb_api` (kept fresh by the separate
5-minute cron whose lock the daily run would otherwise fight).

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


def test_runs_all_three_steps_in_order_and_skips_mlb_api(tmp_path):
    rc, calls, _ = _run(tmp_path)
    assert rc == 0
    lines = calls.strip().splitlines()
    assert lines == ["update --skip mlb_api", "conform", "predict"]


def test_a_failing_step_does_not_skip_the_later_steps(tmp_path):
    rc, calls, log = _run(tmp_path, fail_step="conform")
    # conform failed, but predict was still attempted...
    assert "predict" in calls
    # ...and the overall exit code reflects the failure.
    assert rc != 0
    assert "step conform: FAILED rc=3" in log
    assert "step predict: starting" in log


def test_each_step_is_timestamped_separately(tmp_path):
    _, _, log = _run(tmp_path)
    for step in ("update", "conform", "predict"):
        assert f"step {step}: starting" in log
        assert f"step {step}: ok" in log
