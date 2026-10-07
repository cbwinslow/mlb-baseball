"""Measure every registered dataset against the database and collect the result.

The whole run happens in one READ ONLY transaction: the command cannot write, even by
mistake. Tables that exist in the database but are not registered are still reported,
as "no expectation defined", so nothing passes silently.
"""

import tomllib
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import psycopg

from mlb_baseball import manifest
from mlb_baseball.coverage.model import (
    LABEL_SPECS,
    Dataset,
    Group,
    ManifestFiles,
    NoExpectation,
)
from mlb_baseball.coverage.registry import DATASETS
from mlb_baseball.db import fetch_one, get_connection

ACCEPTED_GAPS_FILE = Path(__file__).with_name("accepted_gaps.toml")
NOT_REGISTERED = "table is not registered in mlb_baseball/coverage/registry.py"


# Statuses that are not a verdict on coverage: nothing was compared, nothing is missing.
NOT_A_GAP = frozenset({"complete", "no_expectation"})


@dataclass(frozen=True)
class AcceptedGap:
    """A known gap the owner accepts: ``max_missing`` is a ceiling, not an exact count."""

    table: str
    group: str | None
    max_missing: int
    reason: str
    owner: str


def load_accepted_gaps(path: Path = ACCEPTED_GAPS_FILE) -> list[AcceptedGap]:
    entries = tomllib.loads(path.read_text())["accepted"]
    return [
        AcceptedGap(e["table"], e.get("group"), e["max_missing"], e["reason"], e["owner"])
        for e in entries
    ]


@dataclass(frozen=True)
class TableReport:
    source: str
    table: str
    unit: str
    status: (
        str  # complete | missing | empty | no_basis | no_expectation | table_absent | inputs_absent
    )
    expectation: str
    rows: int | None
    groups: list[Group]
    fix: str
    caveat: str = ""
    date_column: str = ""
    first_date: str | None = None
    last_date: str | None = None
    date_not_parsed: int | None = None
    live_note: str = ""
    live: list[Group] = field(default_factory=list)
    live_errors: list[str] = field(default_factory=list)

    @property
    def expected(self) -> int:
        return sum(g.expected for g in self.groups)

    @property
    def held(self) -> int:
        return sum(g.held for g in self.groups)

    @property
    def accounted(self) -> int:
        return sum(g.accounted for g in self.groups)

    @property
    def missing(self) -> int:
        return sum(g.missing for g in self.groups)

    @property
    def live_differs(self) -> list[Group]:
        """Seasons where the source's own count and what we hold are not equal."""
        return [g for g in self.live if g.expected != g.held]

    def unexplained(self, accepted: Sequence[AcceptedGap]) -> bool:
        """A gap not covered by an accepted entry. Only a measured shortfall can be
        accepted; an empty, absent or unmeasurable table, or a live disagreement, never is."""
        if not self.is_gap:
            return False
        if self.status != "missing" or self.live_differs or self.live_errors:
            return True
        mine = [a for a in accepted if a.table == self.table]
        whole = [a for a in mine if a.group is None]
        if whole:
            return self.missing > min(a.max_missing for a in whole)
        ceilings = {a.group: a.max_missing for a in mine}
        return any(g.missing > ceilings.get(g.label, 0) for g in self.groups)

    @property
    def is_gap(self) -> bool:
        """Missing, empty, unmeasurable, or the live source disagrees: not a clean result."""
        return self.status not in NOT_A_GAP or bool(self.live_differs or self.live_errors)


@dataclass(frozen=True)
class Report:
    tables: list[TableReport] = field(default_factory=list)

    @property
    def has_gap(self) -> bool:
        return any(t.is_gap for t in self.tables)

    def unexplained(self, accepted: Sequence[AcceptedGap]) -> "Report":
        return Report([t for t in self.tables if t.unexplained(accepted)])

    def only_gaps(self) -> "Report":
        return Report([t for t in self.tables if t.is_gap])

    def sources(self) -> list[str]:
        return sorted({t.source for t in self.tables})


def _exists(cur: psycopg.Cursor, table: str) -> bool:
    cur.execute("SELECT to_regclass(%s) IS NOT NULL", (table,))
    (found,) = fetch_one(cur)
    return bool(found)


def _fix(template: str, groups: Sequence[Group]) -> str:
    years = sorted(int(g.label) for g in groups if g.missing > 0 and g.label.isdigit())
    if years:
        return template.format(first=years[0], last=years[-1])
    return template


def _status(groups: list[Group], rows: int | None) -> str:
    expected = sum(g.expected for g in groups)
    held = sum(g.held for g in groups)
    if expected == 0:
        return "no_basis"
    if held == 0 and not rows:
        return "empty"
    if sum(g.missing for g in groups) > 0:
        return "missing"
    return "complete"


def _data_dates(
    cur: psycopg.Cursor, dataset: Dataset, rows: int | None
) -> tuple[str | None, str | None, int | None]:
    """First date, last date and count of non-date values in the declared date column,
    from ``meta.data_date_range`` (migration 0113); all None when nothing is declared, the
    table is empty, the table lacks the column, or the function is not installed yet."""
    if not dataset.date_column or not rows:
        return None, None, None
    cur.execute("SELECT to_regprocedure('meta.data_date_range(regclass, text)') IS NOT NULL")
    (installed,) = fetch_one(cur)
    if not installed:
        return None, None, None
    cur.execute(
        "SELECT EXISTS (SELECT 1 FROM pg_attribute WHERE attrelid = to_regclass(%s) "
        "AND attname = %s AND attnum > 0 AND NOT attisdropped)",
        (dataset.table, dataset.date_column),
    )
    (has_column,) = fetch_one(cur)
    if not has_column:
        return None, None, None
    cur.execute(
        "SELECT first_date::text, last_date::text, not_date "
        "FROM meta.data_date_range(%s::regclass, %s)",
        (dataset.table, dataset.date_column),
    )
    first, last, bad = fetch_one(cur)
    return first, last, int(bad)


def _measure(cur: psycopg.Cursor, dataset: Dataset, probe: bool = False) -> TableReport:
    spec = dataset.spec
    rows: int | None = None
    if not isinstance(spec, LABEL_SPECS) and _exists(cur, dataset.table):
        cur.execute(f"SELECT count(*) FROM {dataset.table}")
        (rows,) = fetch_one(cur)

    dates = _data_dates(cur, dataset, rows)
    live = dataset.live.measure(cur, dataset.table) if probe and dataset.live and rows else None

    def report(status: str, expectation: str, groups: list[Group]) -> TableReport:
        return TableReport(
            dataset.source,
            dataset.table,
            spec.unit,
            status,
            expectation,
            rows,
            groups,
            _fix(dataset.fix, groups) if status != "complete" else "",
            dataset.caveat,
            dataset.date_column,
            *dates,
            dataset.live.description if live and dataset.live else "",
            live.groups if live else [],
            live.errors if live else [],
        )

    if isinstance(spec, NoExpectation):
        return report("no_expectation", spec.reason, [])
    if isinstance(spec, ManifestFiles) and not manifest.manifest_path(spec.source).exists():
        path = manifest.manifest_path(spec.source)
        return report("inputs_absent", f"{spec.expectation}; {path} does not exist", [])
    absent = [t for t in spec.inputs(dataset.table) if not _exists(cur, t)]
    if dataset.table in absent:
        return report("table_absent", f"{spec.expectation}; the table does not exist", [])
    if absent:
        needs = ", ".join(absent)
        return report("inputs_absent", f"{spec.expectation}; needs {needs}, which do not exist", [])
    groups = spec.measure(cur, dataset.table)
    status = _status(groups, rows)
    expectation = spec.expectation
    if status == "no_basis":
        expectation += "; no final games, ledger items or manifest entries to derive it from"
    return report(status, expectation, groups)


def _matches(dataset: Dataset, source: str | None, table: str | None) -> bool:
    if source is not None and dataset.source != source:
        return False
    if table is None:
        return True
    return table in (dataset.table, dataset.table.removeprefix("raw."))


def _unregistered(cur: psycopg.Cursor, registered: set[str]) -> list[Dataset]:
    cur.execute(
        """
        SELECT 'raw.' || c.relname
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'raw' AND c.relkind IN ('r', 'p')
          AND NOT EXISTS (SELECT 1 FROM pg_inherits i WHERE i.inhrelid = c.oid)
        ORDER BY 1
        """
    )
    return [
        Dataset("unregistered", name, NoExpectation(NOT_REGISTERED))
        for (name,) in cur.fetchall()
        if name not in registered
    ]


def collect(
    *,
    source: str | None = None,
    table: str | None = None,
    datasets: Sequence[Dataset] | None = None,
    probe: bool = False,
) -> Report:
    """Measure ``datasets`` (default: the registry plus any unregistered raw table)."""
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SET TRANSACTION READ ONLY")
        chosen = list(DATASETS if datasets is None else datasets)
        if datasets is None:
            chosen += _unregistered(cur, {d.table for d in chosen})
        reports = [_measure(cur, d, probe) for d in chosen if _matches(d, source, table)]
    return Report(reports)
