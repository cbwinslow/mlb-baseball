"""`scripts/mlb_odds_capture.sh` is a thin cron shim: one run at a time
(`flock`), output appended to `logs/mlb_odds_capture.log`, then `mlb odds-capture`.
The capture itself (game-day gate, both sources) is tested in
tests/integration/test_odds_capture.py.

Driven through the real script with a stub `mlb` so a dropped argument or a lost
exit code would break the production cron with nothing else to catch it.
"""

from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "mlb_odds_capture.sh"


def _run(tmp_path: Path, *, rc: int = 0, lock_held: bool = False) -> tuple[int, str, str]:
    bindir = tmp_path / "bin"
    bindir.mkdir()
    calls_log = tmp_path / "calls.log"
    stub = bindir / "mlb"
    stub.write_text(
        f'#!/usr/bin/env bash\necho "$@" >> "{calls_log}"\necho stub-output\nexit {rc}\n'
    )
    stub.chmod(0o755)

    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    (repo / ".venv" / "bin").mkdir(parents=True)
    (repo / ".venv" / "bin" / "mlb").symlink_to(stub)
    (repo / "scripts" / "mlb_odds_capture.sh").write_text(SCRIPT.read_text())
    (repo / "scripts" / "mlb_odds_capture.sh").chmod(0o755)

    lock = tmp_path / "odds.lock"
    env = dict(
        os.environ,
        MLB_ODDS_LOCK_FILE=str(lock),
        MLB_ODDS_LOG_FILE=str(tmp_path / "odds.log"),
    )
    holder = None
    held = tmp_path / "lock-held"
    try:
        if lock_held:
            # The marker is written only after flock has the lock; waiting on the
            # lock file itself races (flock creates it before acquiring).
            holder = subprocess.Popen(
                ["flock", str(lock), "sh", "-c", f'touch "{held}"; sleep 20'],
                start_new_session=True,
            )
            deadline = time.monotonic() + 10
            while not held.exists():
                assert time.monotonic() < deadline, "lock holder never acquired the lock"
                time.sleep(0.01)
        proc = subprocess.run(
            ["bash", str(repo / "scripts" / "mlb_odds_capture.sh")],
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )
    finally:
        if holder:
            os.killpg(holder.pid, signal.SIGKILL)  # flock and its sleeping child
            holder.wait()
    log = tmp_path / "odds.log"
    return (
        proc.returncode,
        calls_log.read_text() if calls_log.exists() else "",
        log.read_text() if log.exists() else "",
    )


def test_runs_mlb_odds_capture_and_appends_its_output_to_the_log(tmp_path):
    rc, calls, log = _run(tmp_path)
    assert rc == 0
    assert calls.strip().splitlines() == ["odds-capture"]
    assert "stub-output" in log


def test_the_exit_code_of_nightly_is_the_cron_exit_code(tmp_path):
    rc, _, _ = _run(tmp_path, rc=1)
    assert rc == 1


def test_a_second_run_while_one_is_active_skips_without_failing(tmp_path):
    rc, calls, log = _run(tmp_path, lock_held=True)
    assert rc == 0
    assert calls == ""
    assert "already running" in log
