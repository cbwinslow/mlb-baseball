"""`mlb repair`: close coverage gaps that are safe to close, and only those.

openspec/changes/source-inventory, self-repair. The coverage report names the `mlb ingest`
command that fixes each gap. A command runs here only if the table is on `SAFE_REPAIRS`
and the command is exactly the listed one (plus the listed flags), so a changed fix text
can never widen what runs. Each safe table runs at most once a night; three failures in a
row suspend it until a reset row is recorded; everything else is only reported. The commands
are the idempotent connectors, so a second run after the gap closes changes nothing.
"""

import shlex
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from mlb_baseball.coverage.engine import TableReport

SUSPEND_AFTER_FAILURES = 3
FLAG_VALUES = {"--mode": {"backfill"}, "--stage": {"analytics"}}
YEAR_FLAGS = {"--start-year", "--end-year"}


@dataclass(frozen=True)
class SafeRepair:
    """One table whose gap may be closed unattended, by exactly this command."""

    table: str
    argv: tuple[str, ...]
    timeout_seconds: int
    reason: str
    flags: tuple[str, ...] = ()  # the only flags this entry's command may carry, once each


def _mlb_api(table: str) -> SafeRepair:
    return SafeRepair(
        table,
        ("mlb", "ingest", "mlb_api"),
        2 * 3600,
        "per-game load; skips games the ledger holds, so a re-run adds only what is missing",
        ("--stage", "--start-year", "--end-year"),
    )


SAFE_REPAIRS: tuple[SafeRepair, ...] = (
    SafeRepair(
        "raw.statcast_pitch",
        ("mlb", "ingest", "statcast"),
        2 * 3600,
        "loads missing game days only; replaces a day's rows atomically",
    ),
    *(
        _mlb_api(f"raw.{t}")
        for t in (
            "mlb_win_prob",
            "mlb_game_context",
            "mlb_linescore",
            "mlb_playbyplay",
            "mlb_boxscore_batting",
            "mlb_boxscore_pitching",
            "mlb_boxscore_fielding",
            "mlb_umpire",
        )
    ),
    SafeRepair(
        "raw.kalshi_candle",
        ("mlb", "ingest", "kalshi", "--mode", "backfill"),
        4 * 3600,
        "resumable per market via the ledger; time-capped per night",
    ),
    SafeRepair(
        "raw.polymarket_price",
        ("mlb", "ingest", "polymarket", "--mode", "backfill"),
        4 * 3600,
        "resumable per window via the ledger; time-capped per night",
    ),
)
_BY_TABLE = {entry.table: entry for entry in SAFE_REPAIRS}


@dataclass(frozen=True)
class Attempt:
    outcome: str  # ok | failed | reset
    at: datetime


@dataclass(frozen=True)
class Action:
    table: str
    status: str  # planned | report_only | capped | suspended
    argv: tuple[str, ...] = ()
    reason: str = ""
    timeout_seconds: int = 0


@dataclass(frozen=True)
class Result:
    table: str
    outcome: str  # ok | failed
    detail: str = ""


def _matches(entry: SafeRepair, fix: str) -> tuple[str, ...] | None:
    """The fix text as argv if it is the safe command plus only allowed flags, else None."""
    argv = tuple(shlex.split(fix))
    if argv[: len(entry.argv)] != entry.argv:
        return None
    rest = argv[len(entry.argv) :]
    i = 0
    seen: set[str] = set()
    while i < len(rest):
        flag = rest[i]
        value = rest[i + 1] if i + 1 < len(rest) else None
        if flag not in entry.flags or flag in seen:
            return None
        seen.add(flag)
        if flag in YEAR_FLAGS and value is not None and value.isascii() and value.isdigit():
            i += 2
        elif value is not None and value in FLAG_VALUES.get(flag, ()):
            i += 2
        else:
            return None
    return argv


def _suspended(history: Sequence[Attempt]) -> bool:
    """Newest first: the last three outcomes are failures with no reset or success between."""
    run = 0
    for attempt in history:
        if attempt.outcome != "failed":
            break
        run += 1
    return run >= SUSPEND_AFTER_FAILURES


def plan(
    gaps: Sequence[TableReport],
    attempts: dict[str, list[Attempt]],
    now: datetime,
) -> list[Action]:
    """One action per gapped table. Reads nothing, writes nothing."""
    actions = []
    for gap in gaps:
        if not gap.is_gap:
            continue
        entry = _BY_TABLE.get(gap.table)
        argv = _matches(entry, gap.fix) if entry and gap.status == "missing" else None
        if entry is None or argv is None:
            actions.append(Action(gap.table, "report_only", reason=gap.fix))
            continue
        history = attempts.get(gap.table, [])
        if _suspended(history):
            actions.append(Action(gap.table, "suspended", argv, "3 failures in a row"))
        elif any(
            a.outcome != "reset" and a.at.astimezone(UTC).date() == now.date() for a in history
        ):
            actions.append(Action(gap.table, "capped", argv, "already attempted tonight"))
        else:
            actions.append(Action(gap.table, "planned", argv, entry.reason, entry.timeout_seconds))
    return actions


def load_attempts(conn) -> dict[str, list[Attempt]]:
    """Attempts per table, newest first. Empty before migration 0115 has been applied."""
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('meta.repair_attempt') IS NOT NULL")
        if not cur.fetchone()[0]:
            return {}
        cur.execute(
            "SELECT table_name, outcome, attempted_at FROM meta.repair_attempt "
            "ORDER BY attempted_at DESC, id DESC"
        )
        rows = cur.fetchall()
    out: dict[str, list[Attempt]] = {}
    for table, outcome, at in rows:
        out.setdefault(table, []).append(Attempt(outcome, at))
    return out


def record_attempt(conn, table: str, outcome: str, detail: str = "") -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO meta.repair_attempt (table_name, outcome, detail) VALUES (%s, %s, %s)",
            (table, outcome, detail[:500]),
        )
    conn.commit()


def _child_argv(argv: Sequence[str]) -> list[str]:
    """`mlb ...` as this Python's own entry point, so a minimal cron PATH cannot break it."""
    if argv and argv[0] == "mlb":
        return [sys.executable, "-c", "from mlb_baseball.cli import main; main()", *argv[1:]]
    return list(argv)


def run_command(argv: Sequence[str], timeout: float) -> int:
    """Run an `mlb` child process; the exit code, or TimeoutError when it overruns."""
    try:
        return subprocess.run(_child_argv(argv), timeout=timeout, check=False).returncode
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(f"{' '.join(argv)} exceeded {timeout:.0f}s") from exc


def apply(
    actions: Sequence[Action],
    conn,
    runner: Callable[[Sequence[str], float], int] = run_command,
) -> list[Result]:
    """Run the planned actions and record each attempt. Tables that share one command (the
    MLB API per-game tables) run it once; every one of them gets the outcome."""
    results = []
    outcomes: dict[tuple[str, ...], tuple[str, str]] = {}
    for action in actions:
        if action.status != "planned":
            continue
        if action.argv not in outcomes:
            try:
                code = runner(action.argv, action.timeout_seconds)
                outcomes[action.argv] = ("ok" if code == 0 else "failed", f"exit {code}")
            except Exception as exc:  # a hung or crashed command is a failed attempt
                outcomes[action.argv] = ("failed", str(exc))
        outcome, detail = outcomes[action.argv]
        record_attempt(conn, action.table, outcome, detail)
        results.append(Result(action.table, outcome, detail))
    return results


def render(actions: Sequence[Action], results: Sequence[Result], applied: bool) -> str:
    if not actions:
        return "repair: no unexplained gaps"
    done = {r.table: r for r in results}
    lines = [f"repair ({'applied' if applied else 'dry run, nothing written'}):"]
    for a in actions:
        if a.status == "planned":
            verb = done[a.table].outcome if a.table in done else "would run"
            lines.append(f"  {a.table}: {verb}: {' '.join(a.argv)}")
        elif a.status == "report_only":
            lines.append(f"  {a.table}: report only (not on the safe list): {a.reason}")
        else:
            lines.append(f"  {a.table}: {a.status}: {a.reason} ({' '.join(a.argv)})")
    return "\n".join(lines)


def run(
    *,
    apply_changes: bool = False,
    source: str | None = None,
    reset: str | None = None,
    as_json: bool = False,
) -> int:
    """Plan (and with `apply_changes`, run) repairs for unexplained gaps. Exit 1 when a
    safe repair failed, else 0. A dry run reads only."""
    import json

    from mlb_baseball.coverage import collect, load_accepted_gaps
    from mlb_baseball.db import get_connection

    if reset:
        if reset not in _BY_TABLE:
            print(f"repair: {reset} is not on the safe list ({', '.join(sorted(_BY_TABLE))})")
            return 2
        with get_connection() as conn:
            record_attempt(conn, reset, "reset", "owner reset")
        print(f"repair: suspension for {reset} cleared")
        return 0
    report = collect(source=source).unexplained(load_accepted_gaps())
    with get_connection() as conn:
        actions = plan(report.tables, load_attempts(conn), datetime.now(UTC))
        results = apply(actions, conn) if apply_changes else []
    if as_json:
        print(
            json.dumps(
                {
                    "applied": apply_changes,
                    "actions": [a.__dict__ for a in actions],
                    "results": [r.__dict__ for r in results],
                },
                indent=1,
            )
        )
    else:
        print(render(actions, results, apply_changes))
    return 1 if any(r.outcome == "failed" for r in results) else 0
