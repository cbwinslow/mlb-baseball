"""Renders a two-column status table -- table name on the left, a progress
bar on the right -- for every raw/core/gold table in the database, plus a
real-time live view with per-table speed (rows/sec) and ETA while a
bootstrap or backfill is actively running.

Deliberately built from small, swappable pieces rather than one script,
since this is exactly the kind of thing that keeps growing (more tables,
more ways to define "progress," more display styles) as the project does:

- `ProgressStrategy` (a `typing.Protocol`, not a base class someone must
  inherit from -- the modern pythonic way to define an interface without
  forcing a class hierarchy) decides what "percent complete" means for a
  table.
    - `HasDataStrategy` (the fallback every richer strategy defers to):
      100% if the table has any rows, 0% if empty. No assumption about
      how many rows a table "should" have.
    - `RunStatusStrategy`: reads `meta.ingestion_run`'s last status for
      the table's owning source (matched against `registry.CONNECTORS`,
      reused rather than re-hardcoded) -- success/running/failed map to
      100/50/0%.
    - `SeasonCoverageStrategy`: a real, honest percentage for the tables
      this project already knows a true start year for (imported directly
      from each connector's own `FIRST_*_YEAR` constant, e.g.
      `statcast.FIRST_STATCAST_YEAR` -- never re-typed as a second,
      driftable copy) -- `(latest season loaded - first year + 1) /
      (current year - first year + 1)`. Falls back to `HasDataStrategy`
      for every table it doesn't have a real registered start year for,
      rather than guessing one.
  Adding a fourth strategy (e.g. a real expected-row-count check for a
  table `doctor.py` already knows a target for) doesn't require touching
  the collector or renderer below.
- `ProgressBarStyle` (also a Protocol) turns a percent into display text
  for the static table. `AsciiBarStyle` (default) and `BlockBarStyle`
  (unicode) both ship, proving the interface is genuinely swappable.
- `TableStatusCollector` is the only piece that talks to the database --
  row counts and last-run status come from `inventory.py`'s existing
  functions; season coverage is one batched `UNION ALL` query (not one
  query per table) against `SEASON_COVERAGE_REGISTRY`'s tables.
- `StatusTableReport` only renders the static table; it never touches the
  database.
- `watch_live()` is the real-time view: a `rich.progress.Progress` bar per
  table, using the actual `rich` library (already a transitive dependency
  here, now a direct one) instead of hand-rolled speed/ETA math -- `rich`
  already computes a smoothed rows/sec and time-remaining from repeated
  `update(completed=...)` calls, which is a genuinely hard problem to get
  right by hand. Where `SeasonCoverageStrategy` gives a real year, this
  view also derives an *estimated* total row count (rows-per-covered-year
  so far, projected across the remaining known years) so the bar has a
  real percentage and ETA, not just an ever-growing counter -- labeled as
  an estimate, not presented as a hard fact, and only computed from data
  actually observed. Tables with no known start year get an indeterminate
  (pulsing) bar instead: still shows real row count and real rows/sec,
  honestly omits a percentage/ETA it has no basis for.

Static by default (`mlb status`, one collect, one print). `mlb status
--watch SECONDS` switches to the live `rich` view.
"""

import time
from dataclasses import dataclass, field
from typing import Protocol

from rich.progress import (
    BarColumn,
    Progress,
    ProgressColumn,
    SpinnerColumn,
    Task,
    TaskID,
    TaskProgressColumn,
    TextColumn,
    TimeRemainingColumn,
)
from rich.text import Text

from mlb_baseball import inventory
from mlb_baseball.connectors import bref, mlb_api, retrosheet, retrosheet_event, statcast
from mlb_baseball.db import get_connection
from mlb_baseball.registry import CONNECTORS

_RUN_STATUS_PERCENT = {"success": 100.0, "running": 50.0, "failed": 0.0}

# table name -> (first year real data exists, the column holding a row's
# year). Every first-year value is imported from the connector that
# actually defines it -- see the module docstring -- except the two
# retrosheet_event tables, whose earliest year is derived from its own
# PBP_DECADE_ARCHIVES dict rather than a second, hand-typed constant.
_EARLIEST_EVENT_DECADE = min(min(r) for r in retrosheet_event.PBP_DECADE_ARCHIVES.values())
SEASON_COVERAGE_REGISTRY: dict[str, tuple[int, str]] = {
    "retrosheet_allplayers": (retrosheet.FIRST_YEAR, "_season"),
    "retrosheet_batting": (retrosheet.FIRST_YEAR, "_season"),
    "retrosheet_fielding": (retrosheet.FIRST_YEAR, "_season"),
    "retrosheet_gameinfo": (retrosheet.FIRST_YEAR, "_season"),
    "retrosheet_pitching": (retrosheet.FIRST_YEAR, "_season"),
    "retrosheet_plays": (retrosheet.FIRST_YEAR, "_season"),
    "retrosheet_teamstats": (retrosheet.FIRST_YEAR, "_season"),
    "retrosheet_event": (_EARLIEST_EVENT_DECADE, "_season"),
    "retrosheet_game": (_EARLIEST_EVENT_DECADE, "_season"),
    "statcast_pitch": (statcast.FIRST_STATCAST_YEAR, "_season"),
    "bref_batting": (bref.FIRST_YEAR, "_season"),
    "bref_pitching": (bref.FIRST_YEAR, "_season"),
    "mlb_schedule": (mlb_api.FIRST_SCHEDULE_YEAR, "_season"),
    "mlb_roster": (mlb_api.FIRST_ROSTER_YEAR, "_season"),
    "mlb_standing": (mlb_api.FIRST_STANDINGS_YEAR, "_season"),
    "mlb_win_prob": (mlb_api.FIRST_WIN_PROB_YEAR, "_season"),
    "mlb_linescore": (mlb_api.FIRST_WIN_PROB_YEAR, "_season"),
    "mlb_game_context": (mlb_api.FIRST_WIN_PROB_YEAR, "_season"),
    "mlb_transaction": (mlb_api.FIRST_TRANSACTION_YEAR, "_season"),
    "mlb_draft": (mlb_api.FIRST_DRAFT_YEAR, "draft_year"),
}


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
    max_season: int | None = None
    first_year: int | None = None

    @property
    def full_name(self) -> str:
        return f"{self.schema}.{self.table}"

    @property
    def is_populated(self) -> bool:
        return self.rows > 0

    @property
    def has_season_coverage(self) -> bool:
        return self.max_season is not None and self.first_year is not None

    def estimated_total_rows(self, current_year: int) -> int | None:
        """Rows-per-covered-year so far, projected across every year this
        table will eventually cover. A real, data-derived estimate, not a
        guess -- returns None when there isn't enough information yet
        (table not in SEASON_COVERAGE_REGISTRY, or genuinely no rows)."""
        if not self.has_season_coverage or self.rows == 0:
            return None
        assert self.max_season is not None and self.first_year is not None
        years_covered = self.max_season - self.first_year + 1
        if years_covered <= 0:
            return None
        total_years = current_year - self.first_year + 1
        return round(self.rows / years_covered * total_years)


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
    every table, which is why every richer strategy below falls back to
    this one rather than a hard failure."""

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


class SeasonCoverageStrategy:
    """The real one: `(latest season loaded - first year + 1) / (current
    year - first year + 1)`, for the tables in SEASON_COVERAGE_REGISTRY
    (TableStatusCollector is what actually fetches `max_season` -- this
    class only does arithmetic on it). Falls back to HasDataStrategy for
    every table not in that registry, rather than fabricating a number."""

    def __init__(self, current_year: int | None = None) -> None:
        import datetime

        self._current_year = current_year or datetime.date.today().year
        self._fallback = HasDataStrategy()

    def compute(self, status: TableStatus) -> float:
        if not status.has_season_coverage:
            return self._fallback.compute(status)
        assert status.max_season is not None and status.first_year is not None
        total_years = self._current_year - status.first_year + 1
        if total_years <= 0:
            return self._fallback.compute(status)
        covered_years = status.max_season - status.first_year + 1
        return max(0.0, min(100.0, covered_years / total_years * 100))


class ProgressBarStyle(Protocol):
    """Turns a percent into the text shown in the right-hand column of the
    static (non-live) table."""

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


def _ensure_season_indexes(table_names: set[str]) -> None:
    """Creates a season-column index for any SEASON_COVERAGE_REGISTRY table
    that (a) actually exists and (b) doesn't already have one -- most raw
    tables get one for free via load_dataframe's scope_column="_season"
    convention, but a handful (statcast_pitch, retrosheet_event/_game,
    mlb_win_prob/_linescore/_game_context) use a different scope column
    for their own load semantics and never end up with a plain _season
    index otherwise.

    Deliberately NOT a numbered migration: these are all raw tables
    created dynamically by their own connector's first load
    (`load_dataframe`'s CREATE TABLE IF NOT EXISTS), not by any fixed
    migration -- a migration assuming they already exist breaks on any
    environment (a fresh clone, CI, this project's own mlb_test) where
    that connector hasn't run yet. Checking existence first and creating
    lazily, here, is the same "the table might not be there yet" pattern
    load.py itself already uses.

    CREATE INDEX CONCURRENTLY, not a plain CREATE INDEX, and run via a
    temporarily-autocommit connection (same technique migrate.py's own
    nontransactional-migration path uses) -- a real full-history bootstrap
    can be actively inserting into these exact tables while `mlb status`
    runs, and CONCURRENTLY is what avoids taking a lock that would block
    those writes."""
    candidates = {name for name in table_names if name in SEASON_COVERAGE_REGISTRY}
    if not candidates:
        return
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'raw' AND table_name = ANY(%s)",
                (list(candidates),),
            )
            existing_tables = {row[0] for row in cur.fetchall()}
            cur.execute(
                "SELECT tablename FROM pg_indexes WHERE schemaname = 'raw' AND indexname = ANY(%s)",
                ([f"{name}_season_idx" for name in candidates],),
            )
            already_indexed = {row[0] for row in cur.fetchall()}
        conn.commit()

        to_create = existing_tables - already_indexed
        if not to_create:
            return
        old_autocommit = conn.autocommit
        conn.autocommit = True
        try:
            with conn.cursor() as cur:
                for name in to_create:
                    column = SEASON_COVERAGE_REGISTRY[name][1]
                    cur.execute(
                        f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name}_season_idx "
                        f"ON raw.{name} ({column})"
                    )
        finally:
            conn.autocommit = old_autocommit


def _fetch_season_coverage(table_names: set[str]) -> dict[str, int]:
    """One batched query for every table in `table_names` that's also in
    SEASON_COVERAGE_REGISTRY -- not one round-trip per table. Returns
    {table_name: max_season}; a table with no rows yet (or not present in
    the database at all) is simply absent from the result.

    Deliberately MAX(season_column) with no ::int cast, even though the
    result is converted to int in Python right after -- found the hard
    way, by actually timing this against real data: casting per-row in
    SQL (MAX(col::int)) defeats the season column's existing btree index
    (built on the raw text, not the cast expression), forcing a full
    sequential scan. On raw.retrosheet_plays alone (16.7M rows) that's
    13+ seconds; confirmed via EXPLAIN ANALYZE that the uncast MAX() uses
    an index-only backward scan instead, at 0.3ms. Every season value
    here is a plain 4-digit year (confirmed: every real row's _season
    string is exactly 4 characters), so lexicographic MAX on the text
    agrees with numeric MAX -- safe to defer the cast to Python."""
    registered = [name for name in table_names if name in SEASON_COVERAGE_REGISTRY]
    if not registered:
        return {}
    selects = [
        f"SELECT '{name}' AS table_name, MAX({SEASON_COVERAGE_REGISTRY[name][1]}) "
        f"AS max_season FROM raw.{name}"
        for name in registered
    ]
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(" UNION ALL ".join(selects))
            return {row[0]: int(row[1]) for row in cur.fetchall() if row[1] is not None}


class TableStatusCollector:
    """The only class here that touches the database -- row counts and
    last-run status via `inventory.py`'s existing functions, season
    coverage via one batched query (`_fetch_season_coverage`), never a
    query per table."""

    def __init__(self, strategy: ProgressStrategy | None = None) -> None:
        self.strategy: ProgressStrategy = strategy or HasDataStrategy()

    def collect(self) -> list[TableStatus]:
        runs_by_source = {row["source"]: row for row in inventory.last_runs()}
        table_rows = inventory.tables()
        season_by_table = _fetch_season_coverage({row["table"] for row in table_rows})
        statuses = []
        for row in table_rows:
            source = _matching_source_for(row["table"])
            first_year, _ = SEASON_COVERAGE_REGISTRY.get(row["table"], (None, None))
            status = TableStatus(
                schema=row["schema"],
                table=row["table"],
                rows=row["rows"],
                last_run=runs_by_source.get(source) if source else None,
                max_season=season_by_table.get(row["table"]),
                first_year=first_year,
            )
            status.percent = self.strategy.compute(status)
            statuses.append(status)
        return statuses


@dataclass
class StatusTableReport:
    """Renders a collected list of `TableStatus` as a static table --
    never touches the database itself, so it's cheap to unit-test with
    hand-built data."""

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


class RowsPerSecondColumn(ProgressColumn):
    """A generic-unit throughput column for `rich.progress` -- the built-in
    `TransferSpeedColumn` formats bytes/sec (KB, MB, ...), which is the
    wrong unit here. `task.speed` is already computed by `rich` itself
    from repeated `update(completed=...)` calls; this just formats it as
    rows/sec instead of bytes/sec."""

    def render(self, task: "Task") -> Text:
        if task.speed is None:
            return Text("-- rows/s", style="progress.data.speed")
        return Text(f"{task.speed:,.0f} rows/s", style="progress.data.speed")


def watch_live(
    *,
    strategy: ProgressStrategy | None = None,
    populated_only: bool = True,
    refresh_seconds: float = 2.0,
) -> None:
    """The real-time view (`mlb status --watch SECONDS`): one `rich`
    progress bar per table, refreshed every `refresh_seconds`, each
    showing real row count, real rows/sec (from `rich`'s own speed
    tracking), and -- for tables in SEASON_COVERAGE_REGISTRY -- a real
    percentage and ETA against an estimated total (see
    `TableStatus.estimated_total_rows`). Tables without a known start
    year get an indeterminate bar: still-real count and speed, no
    fabricated percentage.

    Static by design otherwise -- this is the one place in the module
    that runs until interrupted, kept separate from the collector/report
    above so the static `mlb status` path never depends on a terminal.

    Ensures the season-coverage indexes described in
    `_ensure_season_indexes` exist before starting, printed so it's a
    visible, explicit action -- not silent, and not something the plain
    `mlb status` snapshot does on your behalf just for looking at a
    table. Deliberately only happens here, in the heavier opt-in live
    view, where fast repeated MAX(_season) queries every refresh cycle
    are actually needed; a one-off `mlb status` doesn't need it and
    shouldn't take on a DDL side effect just to print a table once."""
    import datetime

    current_year = datetime.date.today().year
    all_tables = {row["table"] for row in inventory.tables()}
    to_index = {name for name in all_tables if name in SEASON_COVERAGE_REGISTRY}
    if to_index:
        print(
            f"Ensuring season-coverage indexes exist for {len(to_index)} tables (one-time, safe)..."
        )
        _ensure_season_indexes(all_tables)
    collector = TableStatusCollector(strategy)

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold]{task.fields[full_name]}"),
        BarColumn(),
        TaskProgressColumn(),
        TextColumn("{task.completed:>12,}/{task.fields[total_label]}"),
        RowsPerSecondColumn(),
        TimeRemainingColumn(),
    ) as progress:
        task_ids: dict[str, TaskID] = {}
        # Tracks the max_season each task's `total` was last estimated
        # from -- rich.progress.Progress.update() calls task._reset()
        # (wiping its own speed-tracking sample history) any time `total`
        # differs from its previous value. estimated_total_rows() is
        # recomputed from live row counts every cycle, so passing it to
        # `total=` on every single update() call reset speed tracking
        # every refresh, permanently keeping task.speed at None -- found
        # by directly inspecting rich's own update() source after
        # observing real, confirmed-growing row counts never producing a
        # speed. Only re-baseline `total` when max_season itself changes
        # (a real, infrequent event), not on every row-driven estimate
        # wobble -- lets rich's own speed/ETA math actually accumulate.
        last_baseline_season: dict[str, int | None] = {}
        try:
            while True:
                statuses = collector.collect()
                if populated_only:
                    statuses = [s for s in statuses if s.is_populated]
                for status in statuses:
                    estimated_total = status.estimated_total_rows(current_year)
                    total_label = f"{estimated_total:,.0f} (est.)" if estimated_total else "?"
                    if status.full_name not in task_ids:
                        task_ids[status.full_name] = progress.add_task(
                            status.full_name,
                            total=estimated_total,
                            full_name=status.full_name,
                            total_label=total_label,
                        )
                        last_baseline_season[status.full_name] = status.max_season
                    season_changed = last_baseline_season.get(status.full_name) != status.max_season
                    update_kwargs: dict = {"completed": status.rows, "total_label": total_label}
                    if season_changed:
                        update_kwargs["total"] = estimated_total
                        last_baseline_season[status.full_name] = status.max_season
                    progress.update(task_ids[status.full_name], **update_kwargs)
                time.sleep(refresh_seconds)
        except KeyboardInterrupt:
            pass


def print_status_table(
    *,
    strategy: ProgressStrategy | None = None,
    bar_style: ProgressBarStyle | None = None,
    populated_only: bool = False,
    watch: int | None = None,
) -> None:
    """The CLI entry point (`mlb status`). Static (one collect, one print)
    unless `watch` is set, in which case it switches to the real-time
    `rich`-based `watch_live` view (speed, ETA, live-refreshing bars) until
    interrupted -- a one-shot snapshot is enough most of the time and
    doesn't need to take over the terminal."""
    if watch is not None:
        watch_live(strategy=strategy, populated_only=populated_only, refresh_seconds=float(watch))
        return
    collector = TableStatusCollector(strategy)
    report = StatusTableReport(
        bar_style=bar_style or AsciiBarStyle(), populated_only=populated_only
    )
    print(report.render(collector.collect()))
