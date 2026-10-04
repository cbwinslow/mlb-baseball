"""One optional failure hook: the user's `alert_command` (env `MLB_ALERT_COMMAND`
or `mlb.toml`). No default, so a fresh install only logs. See
openspec/changes/job-retries-alerts/design.md (D3)."""

import logging
import shlex
import subprocess

from mlb_baseball.config import load_settings

logger = logging.getLogger(__name__)

ALERT_TIMEOUT_SECONDS = 30


def alert(message: str) -> bool:
    """Runs the configured command with ``message`` on stdin and as its last
    argument. Returns True only if a command ran and exited zero. The command is
    split with shlex and run without a shell; any failure of the hook is logged
    and swallowed so it never changes the outcome of the job it reports on."""
    logger.error("ALERT: %s", message)
    try:
        command = load_settings().alert_command
        if not command:
            return False
        completed = subprocess.run(
            [*shlex.split(command), message],
            input=message,
            text=True,
            capture_output=True,
            timeout=ALERT_TIMEOUT_SECONDS,
            check=False,
        )
    except Exception as exc:  # the hook must never break the caller
        logger.error("alert_command could not run (%s)", exc)
        return False
    if completed.returncode != 0:
        logger.error(
            "alert_command exited %s: %s", completed.returncode, completed.stderr.strip()[-300:]
        )
        return False
    return True
