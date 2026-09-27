"""Retrosheet tie-out runner: which sources are compared, at which levels, and how.

The pure comparison logic, the register and the read-only connection live in
``mlb_baseball.tieout``. This module owns the parts that know Retrosheet: the
list of sources (each a named, read-only SQL resource under
``mlb_baseball/sql/tieout_*.sql``), which pairs of sources are compared, and the
sequencing. ``scripts/verify_retrosheet_tie_out.py`` is a thin entry point over
``execute``.

Nothing here writes. Every query runs on a connection from
``tieout.open_readonly``.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass

import psycopg

from mlb_baseball import tieout
from mlb_baseball.sql import read_sql
from mlb_baseball.tieout import (
    INITIAL_REGISTER,
    LEVELS,
    Register,
    Report,
    Series,
    TieOutError,
    assess,
    compare,
    coverage,
    fetch_series,
)

Log = Callable[[str], None]

FIRST_SEASON = 1871
LAST_SEASON = 2025  # Retrosheet's most recent published season (see passmarks.md section 3)


@dataclass(frozen=True)
class SourceSpec:
    """One source at one level: the SQL resource and the facts it supplies."""

    name: str
    level: str
    resource: str
    facts: frozenset[str]
    context_only: bool = False  # loaded so a register rule can read it, never compared


def _facts(*names: str) -> frozenset[str]:
    return frozenset(names)


SOURCES: tuple[SourceSpec, ...] = (
    SourceSpec(
        "event", "season", "tieout_season_event.sql", _facts("pa", "k", "bb", "hr", "r", "g")
    ),
    SourceSpec(
        "csv_plays",
        "season",
        "tieout_season_csv_plays.sql",
        _facts("pa", "k", "bb", "hr", "r", "g"),
    ),
    SourceSpec(
        "csv_batting",
        "season",
        "tieout_season_csv_batting.sql",
        _facts("pa", "k", "bb", "hr", "r", "g"),
    ),
    SourceSpec("gameinfo", "season", "tieout_season_gameinfo.sql", _facts("r", "g")),
    SourceSpec("gamelog", "season", "tieout_season_gamelog.sql", _facts("hr", "k", "bb", "r", "g")),
    SourceSpec(
        "gamelog_post",
        "season",
        "tieout_season_gamelog_post.sql",
        _facts("hr", "k", "bb", "r", "g"),
        context_only=True,
    ),
    SourceSpec("box", "season", "tieout_season_box.sql", _facts("hr", "k", "bb", "r", "g")),
)

# Pairs compared at every level a source exists for. The event files are the
# anchor; game info vs game log checks scores and game counts independently of
# the event parser.
PAIRS: tuple[tuple[str, str], ...] = (
    ("event", "csv_plays"),
    ("event", "csv_batting"),
    ("event", "gameinfo"),
    ("event", "gamelog"),
    ("event", "box"),
    ("gameinfo", "gamelog"),
    ("gameinfo", "box"),
)


def sources_for(level: str) -> dict[str, SourceSpec]:
    return {s.name: s for s in SOURCES if s.level == level}


def pairs_for(level: str) -> list[tuple[str, str]]:
    available = sources_for(level)
    return [
        (a, b)
        for a, b in PAIRS
        if a in available
        and b in available
        and not available[a].context_only
        and not available[b].context_only
    ]


def _params(lo: int, hi: int) -> dict[str, int]:
    return {"lo": lo, "hi": hi}


def load_source(conn: psycopg.Connection, spec: SourceSpec, lo: int, hi: int, log: Log) -> Series:
    started = time.monotonic()
    series = fetch_series(
        conn, spec.name, spec.level, spec.facts, read_sql(spec.resource), _params(lo, hi)
    )
    log(
        f"  loaded {spec.level} {spec.name}: {len(series.counts)} keys "
        f"in {time.monotonic() - started:.1f}s"
    )
    return series


def run_season_level(
    conn: psycopg.Connection,
    lo: int,
    hi: int,
    register: Register,
    report: Report,
    ctx: dict[tuple[str, str], Series],
    log: Log,
) -> None:
    """Compare every configured pair of sources at season-total level."""
    log(f"season totals, {lo}-{hi}")
    loaded = {
        name: load_source(conn, spec, lo, hi, log) for name, spec in sources_for("season").items()
    }
    for name, series in loaded.items():
        ctx[(name, "season")] = series
    for a_name, b_name in pairs_for("season"):
        a, b = loaded[a_name], loaded[b_name]
        cov = coverage(a, b)
        comparison = compare(a, b, seasons=cov.comparable)
        report.add(assess(comparison, register, ctx, only_a=cov.only_a, only_b=cov.only_b))


def run_tieout(
    conn: psycopg.Connection,
    *,
    lo: int,
    hi: int,
    levels: Iterable[str] = ("season",),
    register: Register = INITIAL_REGISTER,
    log: Log = print,
) -> Report:
    """Run the requested levels for seasons ``lo``..``hi`` and return the report."""
    wanted = tuple(levels)
    unknown = [level for level in wanted if level not in LEVELS]
    if unknown:
        raise TieOutError(f"unknown level(s) {unknown}; expected some of {LEVELS}")
    if lo > hi:
        raise TieOutError(f"season range is empty: {lo} > {hi}")
    report = Report()
    ctx: dict[tuple[str, str], Series] = {}
    if "season" in wanted:
        run_season_level(conn, lo, hi, register, report, ctx, log)
    return report


def describe_target(conn: psycopg.Connection) -> str:
    """Human-readable target (no password) for the line printed before running."""
    info = conn.info
    return f"database {info.dbname!r} on {info.host or 'local socket'} as {info.user!r}"


def execute(
    *,
    url: str,
    expect_db: str,
    lo: int,
    hi: int,
    levels: Iterable[str],
    dry_run: bool,
    statement_timeout_ms: int,
    out: Log = print,
) -> int:
    """Entry point behind the script. Returns the process exit code:
    0 passed (or dry run ok), 1 the gate failed, 2 it could not run."""
    started = time.monotonic()
    levels = tuple(levels)
    try:
        conn = tieout.open_readonly(
            url, expect_db=expect_db, statement_timeout_ms=statement_timeout_ms
        )
    except (TieOutError, psycopg.Error) as exc:
        out(f"cannot run: {exc}")
        return 2
    try:
        out(f"target: {describe_target(conn)} (read-only)")
        out(f"seasons {lo}-{hi}, levels {', '.join(levels)}")
        if dry_run:
            out("dry run: connection verified read-only and on the expected database; no queries")
            return 0
        try:
            report = run_tieout(conn, lo=lo, hi=hi, levels=levels, log=out)
        except (TieOutError, psycopg.Error) as exc:
            out(f"cannot run: {exc}")
            return 2
    finally:
        conn.close()
    for line in report.lines():
        out(line)
    elapsed = time.monotonic() - started
    out(f"elapsed {elapsed:.1f}s")
    if report.passed:
        out("Retrosheet tie-out PASSED")
        return 0
    out("Retrosheet tie-out FAILED -- see above")
    return 1
