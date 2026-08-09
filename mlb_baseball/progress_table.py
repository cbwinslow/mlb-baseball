"""Renders a two-column status table -- table name on the left, a progress
bar on the right -- for every raw/core/gold table in the database.

Deliberately built from small, swappable pieces rather than one script,
since this is exactly the kind of thing that keeps growing (more tables,
more ways to define "progress," more display styles) as the project does:

- `ProgressStrategy` (a `typing.Protocol`, not a base class someone must
  inherit from -- the modern pythonic way to define an interface without
  forcing a class hierarchy) decides what "percent complete" means for a
  table. `HasDataStrategy` (the default) is the honest, always-correct
  answer with no assumptions: 100% if a table has any rows, 0% if it's
  empty. `RunStatusStrategy` is a richer, opt-in alternative that reads
  `meta.ingestion_run`'s last status for the table's owning source
  (matched against `registry.CONNECTORS`, reused rather than
  re-hardcoded) -- success/running/failed/never-run map to 100/50/0/0%.
  Anyone can add a third strategy (e.g. a real expected-row-count check
  for the handful of tables `doctor.py` already knows a target for)
  without touching the collector or renderer below.
- `ProgressBarStyle` (also a Protocol) turns a percent into display text.
  `AsciiBarStyle` (default, `[####----]`) and `BlockBarStyle` (unicode
  blocks) both ship, proving the interface is genuinely swappable, not
  just planned.
- `TableStatusCollector` is the only piece that talks to the database --
  it reuses `inventory.tables()`/`inventory.last_runs()` rather than
  re-querying `pg_class`/`meta.ingestion_run` itself.
- `StatusTableReport` only renders; it never touches the database. This
  split means the same collected data could feed a future web view or
  JSON export without dragging rendering code along, and the same
  renderer could format fake/test data without a live database.

Static by default (one collect, one render) -- pass `--watch SECONDS` on
the CLI (or `watch=` to `print_status_table`) for a live-refreshing view;
the collect/render split above is what makes that a small addition rather
than a redesign.
"""

import time
from dataclasses import dataclass, field
from typing import Protocol

from mlb_baseball import inventory
from mlb_baseball.registry import CONNECTORS

_RUN_STATUS_PERCENT = {"success": 100.0, "running": 50.0, "failed": 0.0}


def _matching_source_for(table: str) -> str | None:
    """Longest `registry.CONNECTORS` key that prefixes `table` -- e.g.
    raw.retrosheet_event -> "retrosheet_event", not the shorter
    "retrosheet". Shared by RunStatusStrategy and TableStatusCollector so
    the two never drift apart on how a table maps to its owning source."""
    for source in sorted(CONNECTORS, key=len, reverse=True):
        if table.startswith(source):
            return source
    return None


@dataclass
class TableStatus:
    """One table's current state -- purely data, no database access and no
    rendering logic, so it's cheap to construct in a test."""

    schema: str
    table: str
    rows: int
    last_run: dict | None = None
    percent: float = 0.0

    @property
    def full_name(self) -> str:
        return f"{self.schema}.{self.table}"

    @property
    def is_populated(self) -> bool:
        return self.rows > 0


class ProgressStrategy(Protocol):
    """Decides what "percent complete" means for a table. Implement this
    (no inheritance needed -- just match the signature) to add a new
    notion of progress without changing the collector or renderer."""

    def compute(self, status: TableStatus) -> float: ...


class HasDataStrategy:
    """The default: 100% if the table has any rows, 0% if empty. Makes no
    assumption about how many rows a table "should" have -- most raw
    tables have no fixed target (a season's row count depends on the
    season), so guessing one would be dishonest. Always applicable to
    every table, which is why it's the default rather than a richer
    strategy that only works for some."""

    def compute(self, status: TableStatus) -> float:
        return 100.0 if status.is_populated else 0.0


class RunStatusStrategy:
    """Richer, opt-in: reads the owning source's last ingestion run status
    (success/running/failed/never-run) instead of just "has rows." A
    table can be fully populated from a run that's since failed to
    update -- this surfaces that; HasDataStrategy can't. Falls back to
    HasDataStrategy's answer when no source matches (core/gold tables,
    and any raw table whose connector isn't a simple name-prefix match --
    see `_matching_source_for`)."""

    def __init__(self) -> None:
        self._fallback = HasDataStrategy()

    def compute(self, status: TableStatus) -> float:
        source = _matching_source_for(status.table)
        if source is None or status.last_run is None or status.last_run.get("source") != source:
            return self._fallback.compute(status)
        return _RUN_STATUS_PERCENT.get(status.last_run["status"], 0.0)


class ProgressBarStyle(Protocol):
    """Turns a percent into the text shown in the right-hand column."""

    def render(self, percent: float, width: int) -> str: ...


class AsciiBarStyle:
    """`[####------]  40%` -- the default, works in any terminal/log file."""

    def render(self, percent: float, width: int) -> str:
        filled = int(width * max(0.0, min(100.0, percent)) / 100)
        bar = "#" * filled + "-" * (width - filled)
        return f"[{bar}] {percent:5.1f}%"


class BlockBarStyle:
    """`████------  40%` using Unicode block characters -- an alternative
    style proving `ProgressBarStyle` is swappable, not hypothetical."""

    def render(self, percent: float, width: int) -> str:
        filled = int(width * max(0.0, min(100.0, percent)) / 100)
        bar = "█" * filled + "-" * (width - filled)
        return f"{bar} {percent:5.1f}%"


class TableStatusCollector:
    """The only class here that touches the database -- and even then,
    only through `inventory.py`'s existing functions, not a new query."""

    def __init__(self, strategy: ProgressStrategy | None = None) -> None:
        self.strategy: ProgressStrategy = strategy or HasDataStrategy()

    def collect(self) -> list[TableStatus]:
        runs_by_source = {row["source"]: row for row in inventory.last_runs()}
        statuses = []
        for row in inventory.tables():
            source = _matching_source_for(row["table"])
            status = TableStatus(
                schema=row["schema"],
                table=row["table"],
                rows=row["rows"],
                last_run=runs_by_source.get(source) if source else None,
            )
            status.percent = self.strategy.compute(status)
            statuses.append(status)
        return statuses


@dataclass
class StatusTableReport:
    """Renders a collected list of `TableStatus` -- never touches the
    database itself, so it's cheap to unit-test with hand-built data."""

    bar_style: ProgressBarStyle = field(default_factory=AsciiBarStyle)
    bar_width: int = 24
    populated_only: bool = False
    group_by_schema: bool = True

    def render(self, statuses: list[TableStatus]) -> str:
        rows = [s for s in statuses if s.is_populated] if self.populated_only else statuses
        if not rows:
            return "No tables found."
        name_width = max(len(s.full_name) for s in rows)
        lines: list[str] = []
        if self.group_by_schema:
            for schema in dict.fromkeys(s.schema for s in rows):  # preserves first-seen order
                lines.append(f"\n{schema}")
                lines.append("-" * len(schema))
                for s in rows:
                    if s.schema == schema:
                        lines.append(self._row(s, name_width))
        else:
            for s in rows:
                lines.append(self._row(s, name_width))
        return "\n".join(lines).lstrip("\n")

    def _row(self, status: TableStatus, name_width: int) -> str:
        bar = self.bar_style.render(status.percent, self.bar_width)
        return f"  {status.full_name:<{name_width}}  {bar}  {status.rows:>12,} rows"


def print_status_table(
    *,
    strategy: ProgressStrategy | None = None,
    bar_style: ProgressBarStyle | None = None,
    populated_only: bool = False,
    watch: int | None = None,
) -> None:
    """The CLI entry point (`mlb status`). Static (one collect, one print)
    unless `watch` is set, in which case it clears the screen and
    re-collects every `watch` seconds until interrupted -- opt-in, since a
    one-shot snapshot is enough most of the time and doesn't need a
    terminal to itself."""
    collector = TableStatusCollector(strategy)
    report = StatusTableReport(
        bar_style=bar_style or AsciiBarStyle(), populated_only=populated_only
    )
    if watch is None:
        print(report.render(collector.collect()))
        return
    try:
        while True:
            print("\033[2J\033[H", end="")  # clear screen, home cursor
            print(f"mlb status (refreshing every {watch}s -- Ctrl-C to stop)")
            print(report.render(collector.collect()))
            time.sleep(watch)
    except KeyboardInterrupt:
        print("\nstopped.")
