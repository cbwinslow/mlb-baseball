"""Regression coverage proving concurrent pytest sessions no longer collide.

Real incident this replaces: before this change, tests/conftest.py's
mlb-test-suite advisory lock meant a second concurrent `pytest` invocation
against the same base configuration failed immediately (or, before an
earlier fix, hung silently). Each invocation now builds its own uniquely
named, disposable database, so two concurrent sessions must both succeed.
"""

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[2]


def test_concurrent_test_sessions_both_succeed_with_isolated_databases(db_conn):
    # This test is itself running inside a pytest session that already has
    # its own isolated database (tests/conftest.py's postgresql_noproc
    # fixture, built before any test runs). A nested `uv run pytest`
    # invocation against the same base TEST_DATABASE_URL must build its
    # OWN separate database rather than colliding with this session's.
    outer_dbname = db_conn.info.dbname
    env = os.environ.copy()

    result = subprocess.run(
        ["uv", "run", "pytest", "tests/unit/test_config.py", "-q"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "passed" in result.stdout

    probe = subprocess.run(
        [
            "uv",
            "run",
            "python",
            "-c",
            "import runpy; m = runpy.run_path('tests/conftest.py'); print(m['_RUN_DBNAME'])",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert probe.returncode == 0, probe.stdout + probe.stderr
    inner_dbname = probe.stdout.strip()
    assert inner_dbname.startswith("mlb_test_")
    assert inner_dbname != outer_dbname
