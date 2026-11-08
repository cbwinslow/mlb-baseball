"""`mlb nightly`: the daily pipeline as a supervisor over child processes.

Replaces the step logic of scripts/mlb_daily_update.sh. Each step runs as a child
`mlb ...` process, so a crash, kill or out-of-memory death looks the same to the
parent as a non-zero exit. Only `update` is retried (network-bound, and only the
sources without a success tonight); code-bound steps are reported at once. Every
step attempt is one `meta.ingestion_run` row (mode 'nightly'); a failed step calls
the `alert_command` hook once. See openspec/changes/job-retries-alerts/design.md
and the job-reliability spec. The step order and gates are the 2026-09-27
incident fixes the shell script carried (migrate first, report only after a good
conform).
"""

import json
import logging
import os
import subprocess
import sys
import threading
import time
from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from mlb_baseball import ingest
from mlb_baseball.alert import alert
from mlb_baseball.db import get_connection

logger = logging.getLogger(__name__)

# Child processes run the same entry point as the `mlb` console script.
CHILD_COMMAND = (sys.executable, "-c", "from mlb_baseball.cli import main; main()")
# mlb_api is kept fresh by its own 5-minute cron and holds its lock at 06:00.
EXCLUDED_SOURCES = ("mlb_api",)
DEFAULT_RETRY_PAUSES = (60.0, 300.0)  # seconds before retry 2 and retry 3
LOG_TAIL_LINES = 15
# A step that runs longer is killed and reported as failed, so a hung child cannot
# block the run (and hold the shell shim's flock) without any alert. The longest
# step today (predict) takes under an hour.
STEP_TIMEOUT_SECONDS = 4 * 3600
# `repair-runs` is a few quick queries; a hung one must not hold up the retry loop.
REPAIR_TIMEOUT_SECONDS = 300


# A run that started but has not finished after this long is reported as dead
# (the slowest recorded night is under four hours); a night with no start in this
# long is reported as never run. Both are checked by `mlb nightly --check`, which
# runs from cron, outside the process it watches.
RUN_WINDOW = timedelta(hours=5)
MAX_RUN_GAP = timedelta(hours=26)


def default_marker_path() -> Path:
    return Path(os.environ.get("MLB_HOME", Path.home() / ".mlb")) / "nightly_run.json"


@dataclass(frozen=True)
class StepResult:
    name: str
    ok: bool
    attempts: int = 1
    health: bool = False


def _log(message: str) -> None:
    print(f"{datetime.now(UTC):%Y-%m-%dT%H:%M:%SZ} {message}", flush=True)


def write_marker(
    path: Path, started_at: datetime, finished_at: datetime | None, rc: int | None
) -> None:
    """The run's own record, independent of the database. Bookkeeping must never
    fail the pipeline, so a write error is logged."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(
                {
                    "started_at": started_at.isoformat(),
                    "finished_at": finished_at.isoformat() if finished_at else None,
                    "rc": rc,
                }
            )
        )
        tmp.replace(path)
    except OSError as exc:
        logger.error("could not write the run marker %s (%s)", path, exc)


def check_marker(path: Path, now: datetime) -> str | None:
    """Why the last nightly run needs attention, or None. A finished run is fine
    even with rc=1: its failing step already sent its own alert."""
    try:
        data = json.loads(path.read_text())
        started = datetime.fromisoformat(data["started_at"])
        finished = data["finished_at"]
    except FileNotFoundError:
        return f"mlb nightly: no nightly run record at {path}; it may never have started"
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return f"mlb nightly: run record {path} is unreadable ({exc})"
    if finished is None:
        if now - started > RUN_WINDOW:
            return (
                f"mlb nightly: the run started {started:%Y-%m-%d %H:%M}Z did not finish "
                f"within {RUN_WINDOW}; the process may have died"
            )
        return None
    if now - started > MAX_RUN_GAP:
        return (
            f"mlb nightly: last run started {started:%Y-%m-%d %H:%M}Z; tonight's run did not start"
        )
    return None


def run_child(
    command: Sequence[str],
    args: Sequence[str],
    env: dict[str, str] | None = None,
    timeout: float = STEP_TIMEOUT_SECONDS,
) -> tuple[int, list[str]]:
    """Runs ``mlb <args>`` as a child, echoing its output as it arrives. Returns
    (exit code, last few output lines). A negative code means it was killed by a
    signal, including by the ``timeout`` watchdog (the tail then ends with a
    timeout line)."""
    tail: deque[str] = deque(maxlen=LOG_TAIL_LINES)
    timed_out = threading.Event()
    with subprocess.Popen(
        [*command, *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env={**os.environ, **(env or {})},
    ) as proc:

        def _kill() -> None:
            timed_out.set()
            proc.kill()

        watchdog = threading.Timer(timeout, _kill)
        watchdog.start()
        assert proc.stdout is not None
        try:
            for line in proc.stdout:
                print(line, end="", flush=True)
                tail.append(line.rstrip())
        finally:
            watchdog.cancel()
    if timed_out.is_set():
        message = f"killed after exceeding the {timeout:.0f}s step timeout"
        _log(message)
        tail.append(message)
    return proc.returncode, list(tail)


def record_step(
    step: str,
    attempt: int,
    status: str,
    started_at: datetime,
    finished_at: datetime,
    error: str | None,
) -> None:
    """One finished meta.ingestion_run row per step attempt. Written after the
    step ends (so `migrate` has already added the columns this needs). A
    bookkeeping failure is logged, never allowed to fail the pipeline."""
    try:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO meta.ingestion_run "
                "(source, mode, status, error, started_at, finished_at, pid, attempt) "
                "VALUES (%s, 'nightly', %s, %s, %s, %s, %s, %s)",
                (step, status, error, started_at, finished_at, os.getpid(), attempt),
            )
    except Exception as exc:
        logger.error("could not record step %s attempt %s (%s)", step, attempt, exc)


def sources_without_success(expected: Sequence[str], since: datetime) -> list[str] | None:
    """Sources in ``expected`` with no successful update run started since
    ``since``; None if the database cannot be asked."""
    try:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT source FROM meta.ingestion_run "
                "WHERE mode = 'update' AND status = 'success' AND started_at >= %s",
                (since,),
            )
            done = {row[0] for row in cur.fetchall()}
    except Exception as exc:
        logger.error("could not read update results (%s)", exc)
        return None
    return [s for s in expected if s not in done]


def last_errors(sources: Sequence[str], since: datetime) -> str:
    """Latest recorded error per failing source, for the alert text. Best effort."""
    try:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT ON (source) source, error FROM meta.ingestion_run "
                "WHERE mode = 'update' AND status = 'failed' AND source = ANY(%s) "
                "AND started_at >= %s ORDER BY source, id DESC",
                (list(sources), since),
            )
            return "; ".join(f"{s}: {(e or '')[:120]}" for s, e in cur.fetchall())
    except Exception:
        return ""


QUERY_STAT_RETENTION_DAYS = 180

_SNAPSHOT_SQL = """
INSERT INTO meta.query_stat_snapshot
    (snapshot_at, queryid, calls, total_exec_time_ms, rows, shared_blks_hit,
     shared_blks_read, temp_blks_written, wal_bytes, query)
SELECT %s, queryid, sum(calls), sum(total_exec_time), sum(rows), sum(shared_blks_hit),
       sum(shared_blks_read), sum(temp_blks_written), sum(wal_bytes),
       left(min(query), 1000)
FROM pg_stat_statements
WHERE dbid = (SELECT oid FROM pg_database WHERE datname = current_database())
  AND queryid IS NOT NULL
GROUP BY queryid
"""


def snapshot_query_stats() -> int | None:
    """Copies pg_stat_statements into meta.query_stat_snapshot and prunes old
    snapshots. Returns the rows written, or None when it could not (extension
    missing, no permission): telemetry must never fail the pipeline."""
    try:
        with get_connection() as conn, conn.cursor() as cur:
            now = datetime.now(UTC)
            cur.execute(_SNAPSHOT_SQL, (now,))
            written = cur.rowcount
            cur.execute(
                "DELETE FROM meta.query_stat_snapshot "
                "WHERE snapshot_at < %s - make_interval(days => %s)",
                (now, QUERY_STAT_RETENTION_DAYS),
            )
            return written
    except Exception as exc:
        logger.error("could not snapshot pg_stat_statements (%s)", exc)
        return None


def prune_monitor() -> bool:
    """Deletes old run-monitor rows (meta.prune_ops). Telemetry housekeeping must
    never fail the pipeline, so a failure is logged and reported as False."""
    try:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                "CALL meta.prune_ops(make_interval(days => %s))", (QUERY_STAT_RETENTION_DAYS,)
            )
            conn.commit()
        return True
    except Exception as exc:
        logger.error("could not prune the run monitor tables (%s)", exc)
        return False


class Nightly:
    def __init__(
        self,
        *,
        command: Sequence[str] = CHILD_COMMAND,
        sources: Sequence[str] | None = None,
        retry_pauses: Sequence[float] = DEFAULT_RETRY_PAUSES,
        notify: Callable[[str], object] = alert,
        sleep: Callable[[float], None] = time.sleep,
        marker_path: Path | None = None,
    ) -> None:
        self.command = command
        self._sources = sources
        self.retry_pauses = tuple(retry_pauses)
        self.notify = notify
        self.sleep = sleep
        self.marker_path = marker_path or default_marker_path()
        self.results: list[StepResult] = []
        self._started = datetime.now(UTC)
        self.health_findings: list[str] = []

    def _repair_runs(self) -> None:
        """Marks `running` rows of dead processes failed. Bounded by its own short
        timeout; a failure is logged and never stops the pipeline."""
        code, tail = run_child(self.command, ["repair-runs"], timeout=REPAIR_TIMEOUT_SECONDS)
        if code != 0:
            _log(f"repair-runs failed (rc={code}): {tail[-1] if tail else 'no output'}")

    @property
    def sources(self) -> list[str]:
        if self._sources is None:
            from mlb_baseball.registry import CONNECTORS

            return [n for n in CONNECTORS if n not in EXCLUDED_SOURCES]
        return list(self._sources)

    def step(self, name: str, args: Sequence[str], *, health: bool = False) -> bool:
        """Runs one code-bound step once. A pipeline step alerts at once on failure.
        A health step (a check of the data, not a stage of the pipeline) does not
        alert or change the exit code; its finding goes into the end-of-run digest."""
        started = datetime.now(UTC)
        _log(f"step {name}: starting")
        code, tail = run_child(self.command, args)
        finished = datetime.now(UTC)
        ok = code == 0
        took = int((finished - started).total_seconds())
        if ok:
            _log(f"step {name}: ok (took {took}s)")
        else:
            _log(f"step {name}: FAILED rc={code} (took {took}s)")
            if health:
                self.health_findings.append(
                    f"{name} (rc={code}): {tail[-1] if tail else 'no output'}"
                )
            else:
                self.notify(
                    f"mlb nightly: step {name} failed (rc={code}). Last output:\n" + "\n".join(tail)
                )
        record_step(
            name,
            1,
            "success" if ok else "failed",
            started,
            finished,
            None if ok else f"rc={code}: " + " | ".join(tail[-3:]),
        )
        self.results.append(StepResult(name, ok, health=health))
        return ok

    def update(self) -> bool:
        """`update` with bounded retries of only the sources not yet successful."""
        night_start = datetime.now(UTC)
        expected = self.sources
        pending = list(expected)
        attempts = len(self.retry_pauses) + 1
        for attempt in range(1, attempts + 1):
            skip = [s for s in expected if s not in pending]
            args = ["update"]
            for source in (*EXCLUDED_SOURCES, *skip):
                args += ["--skip", source]
            started = datetime.now(UTC)
            _log(f"step update: attempt {attempt}/{attempts} for {', '.join(pending)}")
            code, tail = run_child(self.command, args, {ingest.ATTEMPT_ENV: str(attempt)})
            finished = datetime.now(UTC)
            self._repair_runs()  # reap rows of a killed child
            remaining = sources_without_success(expected, night_start)
            if remaining is None:
                remaining = list(pending) if code != 0 else []
            ok = not remaining
            record_step(
                "update",
                attempt,
                "success" if ok else "failed",
                started,
                finished,
                None if ok else f"rc={code}; no success yet: {', '.join(remaining)}",
            )
            if ok:
                _log(f"step update: ok after {attempt} attempt(s)")
                self.results.append(StepResult("update", True, attempt))
                return True
            pending = remaining
            if attempt < attempts:
                pause = self.retry_pauses[attempt - 1]
                _log(f"step update: {', '.join(pending)} not done; retrying in {pause:.0f}s")
                self.sleep(pause)
        _log(f"step update: FAILED after {attempts} attempts: {', '.join(pending)}")
        self.notify(
            f"mlb nightly: step update failed after {attempts} attempts. "
            f"Sources without success: {', '.join(pending)}. "
            f"{last_errors(pending, night_start)}\n" + "\n".join(tail)
        )
        self.results.append(StepResult("update", False, attempts))
        return False

    def run(self) -> int:
        """The whole pipeline; returns the process exit code (0 only if every step passed)."""
        _log("starting nightly update")
        self._started = datetime.now(UTC)
        write_marker(self.marker_path, self._started, None, None)
        # Clear rows left 'running' by a process that was killed (issue #180).
        self._repair_runs()
        if not self.step("migrate", ["migrate"]):
            _log("migrate failed; skipping update, conform, report, predict")
            return self._finish()
        self.update()
        if self.step("conform", ["conform"]):
            self.step("report", ["report"])
        else:
            _log("conform failed; skipping report")
        self.step("predict", ["predict"])
        # Checks of the data rather than builds of it: a finding is reported in one digest
        # and does not fail the night.
        self.step("populated", ["doctor", "--populated"], health=True)
        # Drift fails the step (a source changed shape; exit 1). An unreachable source is
        # shown as UNCHECKED in the log and in meta.schema_finding but does not alert every
        # night (design: "unchecked instead of failing").
        self.step("schema-watch", ["schema-watch", "--tolerate-unchecked"], health=True)
        # Repair closes the gaps on its short safe list (Statcast days, MLB per-game tables,
        # new Kalshi and Polymarket markets), then the check measures what is left, so a gap
        # that the repair fixed does not alert and one that it cannot fix does. Both read the
        # report in `--light` form: the row counts and date ranges took over half an hour.
        # Repair writes data, so a failed repair is a pipeline failure, not a health finding.
        self.step("repair", ["repair", "--apply"])
        self.step(
            "coverage",
            ["coverage", "--unexplained", "--missing-only", "--fail-on-gap", "--light"],
            health=True,
        )
        written = snapshot_query_stats()
        _log(f"query stats snapshot: {'skipped' if written is None else f'{written} statements'}")
        _log(f"run monitor prune: {'done' if prune_monitor() else 'skipped'}")
        return self._finish()

    def _finish(self) -> int:
        failed = [r.name for r in self.results if not r.ok and not r.health]
        rc = 1 if failed else 0
        if self.health_findings:
            self.notify(
                "mlb nightly health digest (the pipeline itself "
                + ("FAILED" if failed else "ran")
                + "): "
                + "; ".join(self.health_findings)
            )
        _log(f"finished nightly update (overall rc={rc})")
        write_marker(self.marker_path, self._started, datetime.now(UTC), rc)
        return rc
