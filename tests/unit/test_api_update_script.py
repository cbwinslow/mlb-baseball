"""`scripts/mlb_api_update.sh` runs every 5 minutes. It failed for days without anyone
knowing (2026-11-25 to 27), so repeated failure must raise one alert.

Driven through the real script with a stub `mlb` and the real `mlb_alert.sh`, writing to
a temporary alert home with no remote channel configured.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


class Cron:
    def __init__(self, tmp_path: Path) -> None:
        self.root = tmp_path
        repo = tmp_path / "repo"
        (repo / "scripts").mkdir(parents=True)
        (repo / ".venv" / "bin").mkdir(parents=True)
        for name in ("mlb_api_update.sh", "mlb_alert.sh"):
            (repo / "scripts" / name).write_text((SCRIPTS / name).read_text())
            (repo / "scripts" / name).chmod(0o755)
        self.rc_file = tmp_path / "rc"
        stub = repo / ".venv" / "bin" / "mlb"
        stub.write_text(f'#!/usr/bin/env bash\necho stub-output\nexit "$(cat "{self.rc_file}")"\n')
        stub.chmod(0o755)
        self.script = repo / "scripts" / "mlb_api_update.sh"
        self.env = {
            "PATH": os.environ["PATH"],
            "HOME": str(tmp_path),
            "MLB_HOME": str(tmp_path / "alerts"),
            "MLB_API_LOCK_FILE": str(tmp_path / "api.lock"),
        }

    def run(self, rc: int) -> int:
        self.rc_file.write_text(str(rc))
        return subprocess.run(
            ["bash", str(self.script)], env=self.env, timeout=30, check=False
        ).returncode

    def alerts(self) -> list[str]:
        path = self.root / "alerts" / "alerts.log"
        return path.read_text().splitlines() if path.exists() else []


def test_exit_code_and_output_reach_cron_and_the_log(tmp_path):
    cron = Cron(tmp_path)

    assert (cron.run(0), cron.run(3)) == (0, 3)
    log = (tmp_path / "repo" / "logs" / "mlb_api_update.log").read_text()
    assert "stub-output" in log and "finished mlb_api update" in log


def test_three_failures_in_a_row_raise_exactly_one_alert(tmp_path):
    cron = Cron(tmp_path)

    cron.run(1)
    cron.run(1)
    assert cron.alerts() == []
    cron.run(1)
    cron.run(1)
    assert len(cron.alerts()) == 1
    assert "mlb_api update has failed 3 times in a row" in cron.alerts()[0]


def test_a_success_resets_the_count(tmp_path):
    cron = Cron(tmp_path)

    for rc in (1, 1, 0, 1, 1):
        cron.run(rc)
    assert cron.alerts() == []
    cron.run(1)
    assert len(cron.alerts()) == 1
