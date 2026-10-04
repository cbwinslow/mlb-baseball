"""`mlb runs`: each scheduled job's last result, age and duration from one query
on `meta.ingestion_run`; `--check` flags a failed or stale job. Unlike `mlb
status` it counts no tables. See openspec/changes/job-retries-alerts (D4)."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from mlb_baseball.db import get_connection
from mlb_baseball.health import DAILY_FRESHNESS_THRESHOLD_MINUTES

# Jobs that stopped running more than this long ago are retired, not stale.
ACTIVE_WINDOW_DAYS = 14
# Only scheduled modes: bootstrap, backfill, features and backup are run by hand.
TRACKED_MODES = ("update", "nightly")
# Sources with a faster cadence than daily (scripts/mlb_api_update.sh, every 5 min).
THRESHOLD_MINUTES = {"mlb_api": 15}

_QUERY = """
WITH last AS (
    SELECT DISTINCT ON (source, mode)
           source, mode, status, attempt, started_at, finished_at, error
    FROM meta.ingestion_run
    WHERE mode = ANY(%s)
    ORDER BY source, mode, id DESC
), ok AS (
    SELECT source, mode, max(finished_at) AS success_at
    FROM meta.ingestion_run
    WHERE status = 'success' AND mode = ANY(%s)
    GROUP BY source, mode
)
SELECT last.source, last.mode, last.status, last.attempt, last.started_at,
       last.finished_at, last.error, ok.success_at
FROM last LEFT JOIN ok USING (source, mode)
WHERE last.started_at > now() - make_interval(days => %s)
ORDER BY last.source, last.mode
"""


@dataclass(frozen=True)
class JobRun:
    source: str
    mode: str
    status: str
    attempt: int
    started_at: datetime
    finished_at: datetime | None
    error: str | None
    success_at: datetime | None

    @property
    def job(self) -> str:
        return f"{self.source}:{self.mode}"

    @property
    def threshold(self) -> timedelta:
        return timedelta(
            minutes=THRESHOLD_MINUTES.get(self.source, DAILY_FRESHNESS_THRESHOLD_MINUTES)
        )

    def duration(self) -> timedelta | None:
        return None if self.finished_at is None else self.finished_at - self.started_at

    def problem(self, now: datetime) -> str | None:
        """Why this job needs attention, or None. A run still in progress is not
        a failure; it is stale only if no success is recent enough."""
        if self.status == "failed":
            return f"last run failed: {(self.error or 'no error recorded')[:200]}"
        if self.success_at is None:
            return "no successful run recorded"
        age = now - self.success_at
        if age > self.threshold:
            return f"no success for {_human(age)} (limit {_human(self.threshold)})"
        return None


def fetch_runs() -> list[JobRun]:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(_QUERY, (list(TRACKED_MODES), list(TRACKED_MODES), ACTIVE_WINDOW_DAYS))
        return [JobRun(*row) for row in cur.fetchall()]


def _human(delta: timedelta) -> str:
    seconds = int(delta.total_seconds())
    if seconds < 90:
        return f"{seconds}s"
    if seconds < 90 * 60:
        return f"{round(seconds / 60)}m"
    return f"{seconds / 3600:.1f}h"


def render(runs: list[JobRun], now: datetime) -> str:
    lines = [f"{'job':34} {'last':8} {'try':>3} {'ended ago':>10} {'took':>8}  note"]
    for run in runs:
        ended = run.finished_at or run.started_at
        took = run.duration()
        problem = run.problem(now)
        state = "STALE" if problem and run.status != "failed" else run.status
        lines.append(
            f"{run.job:34} {state:8} {run.attempt:>3} {_human(now - ended):>10} "
            f"{_human(took) if took is not None else '-':>8}  {problem or ''}"
        )
    return "\n".join(lines)


def check(runs: list[JobRun], now: datetime) -> list[str]:
    """One line per job that failed last or has no recent enough success."""
    return [f"{run.job}: {problem}" for run in runs if (problem := run.problem(now))]


def _now() -> datetime:
    """The clock `main` reads; tests replace it so fixed-date fixtures do not age."""
    return datetime.now(UTC)


def main(*, check_only: bool, notify) -> int:
    """Prints the table; with ``check_only`` returns 1 (after calling ``notify``
    once with all problems) when any job needs attention."""
    now = _now()
    runs = fetch_runs()
    print(render(runs, now))
    if not check_only:
        return 0
    problems = check(runs, now)
    if not problems:
        return 0
    notify("mlb runs --check: " + "; ".join(problems))
    return 1
