"""`scripts/fangraphs_update.sh` runs `mlb ingest fangraphs --mode update`
under flock: an overlapping run is skipped, not stacked (ADR-288 — the job
fires every 6h to capture projection movement and a slow/retried run must not
collide with the next tick).

Driven through the real script with a stub `mlb` on PATH.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "fangraphs_update.sh"


def _repo_with_stub(tmp_path: Path, *, mlb_body: str) -> tuple[Path, Path]:
    bindir = tmp_path / "bin"
    bindir.mkdir()
    calls_log = tmp_path / "calls.log"
    stub = bindir / "mlb"
    stub.write_text(f'#!/usr/bin/env bash\necho "$@" >> "{calls_log}"\n{mlb_body}\n')
    stub.chmod(0o755)

    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    (repo / ".venv" / "bin").mkdir(parents=True)
    (repo / ".venv" / "bin" / "mlb").symlink_to(stub)
    (repo / "scripts" / "fangraphs_update.sh").write_text(SCRIPT.read_text())
    (repo / "scripts" / "fangraphs_update.sh").chmod(0o755)
    return repo, calls_log


def _env(tmp_path: Path) -> dict:
    return dict(
        os.environ,
        MLB_FANGRAPHS_LOCK_FILE=str(tmp_path / "fangraphs.lock"),
        MLB_FANGRAPHS_LOG_FILE=str(tmp_path / "fangraphs.log"),
    )


def test_runs_ingest_fangraphs_update(tmp_path):
    repo, calls_log = _repo_with_stub(tmp_path, mlb_body="exit 0")
    env = _env(tmp_path)

    proc = subprocess.run(
        ["bash", str(repo / "scripts" / "fangraphs_update.sh")],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )

    assert proc.returncode == 0
    assert calls_log.read_text().strip() == "ingest fangraphs --mode update"
    log = (tmp_path / "fangraphs.log").read_text()
    assert "starting fangraphs update" in log
    assert "finished fangraphs update" in log


def test_second_invocation_skips_while_the_lock_is_held(tmp_path):
    # A stub that blocks until a sentinel file appears -> the first run holds
    # the flock while the second run fires.
    repo, calls_log = _repo_with_stub(
        tmp_path,
        mlb_body=f'while [ ! -f "{tmp_path / "release"}" ]; do sleep 0.05; done\nexit 0',
    )
    env = _env(tmp_path)

    first = subprocess.Popen(
        ["bash", str(repo / "scripts" / "fangraphs_update.sh")],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        text=True,
    )
    try:
        # Wait until the first run has actually acquired the lock and called mlb.
        deadline = 10.0
        while deadline > 0 and not calls_log.exists():
            import time

            time.sleep(0.1)
            deadline -= 0.1
        assert calls_log.exists(), "first run never started"

        second = subprocess.run(
            ["bash", str(repo / "scripts" / "fangraphs_update.sh")],
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )
        assert second.returncode == 0
        assert "already running, skipping this tick" in (tmp_path / "fangraphs.log").read_text()
        # The blocked-out second run must not have invoked mlb a second time.
        assert calls_log.read_text().count("ingest fangraphs --mode update") == 1
    finally:
        (tmp_path / "release").write_text("go")
        first.wait(timeout=30)

    assert calls_log.read_text().count("ingest fangraphs --mode update") == 1
