"""Regression coverage for the fail-fast fix to tests/conftest.py's
mlb-test-suite reservation lock.

Real incident, not hypothetical: two Claude Code sessions running the full
suite against the same mlb_test at once used to mean the second session's
own conftest.py fixture silently blocked on `pg_advisory_lock` -- often for
the entire duration of the first session's run -- with no indication of what
it was waiting on. conftest.py now uses `pg_try_advisory_lock` and fails
immediately with the colliding PID instead.
"""

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[2]


def test_concurrent_test_session_fails_fast_instead_of_hanging():
    # This test is itself running inside a pytest session that already holds
    # the mlb-test-suite advisory lock (conftest.py's autouse session
    # fixture, acquired before any test runs) -- so a nested `uv run pytest`
    # invocation against the same database naturally reproduces the exact
    # collision this fix exists for. No need to fake a second lock holder.
    env = os.environ.copy()
    env["TEST_DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", "postgresql:///mlb_test")

    result = subprocess.run(
        ["uv", "run", "pytest", "tests/unit/test_config.py", "-q"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 1
    combined = result.stdout + result.stderr
    assert "already reserved by another test session" in combined
    assert "pid " in combined  # names the actual colliding PID, not just "someone"
