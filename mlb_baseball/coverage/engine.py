"""Measure every registered dataset against the database and collect the result.

The whole run happens in one READ ONLY transaction: the command cannot write, even by
mistake. Tables that exist in the database but are not registered are still reported,
as "no expectation defined", so nothing passes silently.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field

import psycopg

from mlb_baseball.coverage.model import Dataset, Group, ManifestFiles, NoExpectation
from mlb_baseball.coverage.registry import DATASETS
from mlb_baseball.db import fetch_one, get_connection

NOT_REGISTERED = "table is not registered in mlb_baseball/coverage/registry.py"


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


@dataclass(frozen=True)
class Report:
    tables: list[TableReport] = field(default_factory=list)

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


def _measure(cur: psycopg.Cursor, dataset: Dataset) -> TableReport:
    spec = dataset.spec
    rows: int | None = None
    if not isinstance(spec, ManifestFiles) and _exists(cur, dataset.table):
        cur.execute(f"SELECT count(*) FROM {dataset.table}")
        (rows,) = fetch_one(cur)

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
        )

    if isinstance(spec, NoExpectation):
        return report("no_expectation", spec.reason, [])
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
) -> Report:
    """Measure ``datasets`` (default: the registry plus any unregistered raw table)."""
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SET TRANSACTION READ ONLY")
        chosen = list(DATASETS if datasets is None else datasets)
        if datasets is None:
            chosen += _unregistered(cur, {d.table for d in chosen})
        reports = [_measure(cur, d) for d in chosen if _matches(d, source, table)]
    return Report(reports)
