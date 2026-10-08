"""Text, JSON and markdown views of a coverage ``Report``. The JSON has no timestamps and
sorted keys, so two runs against the same database are byte-identical."""

import json

from mlb_baseball.coverage.engine import Report, TableReport
from mlb_baseball.coverage.model import SCHEDULE_SETTLED_LABEL

MAX_MISSING_ITEMS = 25
STATUS_LABEL = {
    "complete": "complete",
    "missing": "MISSING",
    "empty": "EMPTY: nothing held",
    "no_basis": "NO BASIS: nothing to derive an expectation from",
    "no_expectation": "no expectation defined",
    "table_absent": "TABLE DOES NOT EXIST",
    "inputs_absent": "CANNOT MEASURE: an input table or file does not exist",
}


def _by_source(report: Report) -> dict[str, list[TableReport]]:
    grouped: dict[str, list[TableReport]] = {}
    for table in sorted(report.tables, key=lambda t: (t.source, t.table)):
        grouped.setdefault(table.source, []).append(table)
    return grouped


def missing_text(table: TableReport) -> str:
    """Compact list of what is missing: ``1999: 3 games``; whole seasons as ranges."""
    groups = [g for g in table.groups if g.missing > 0]
    if table.unit == "season":
        years = sorted(int(g.label) for g in groups)
        items: list[str] = []
        start = previous = None
        for year in [*years, None]:
            if start is not None and (year is None or year != previous + 1):  # type: ignore[operator]
                span = f"{start}" if start == previous else f"{start}-{previous}"
                count = previous - start + 1  # type: ignore[operator]
                items.append(f"{span} ({count} season{'s' if count != 1 else ''})")
                start = None
            if year is not None:
                start = year if start is None else start
                previous = year
    else:
        items = [
            f"{g.label}: {g.missing} {table.unit}{'s' if g.missing != 1 else ''}" for g in groups
        ]
    if len(items) > MAX_MISSING_ITEMS:
        items = [*items[:MAX_MISSING_ITEMS], f"... and {len(items) - MAX_MISSING_ITEMS} more"]
    return "; ".join(items)


def _plural(count: int, unit: str) -> str:
    return f"{count:,} {unit}{'s' if count != 1 else ''}"


def _live_text(table: TableReport) -> list[str]:
    if not table.live and not table.live_errors:
        return []
    differs = table.live_differs
    lines = [
        f"    live check: {table.live_note}; {len(table.live)} compared, {len(differs)} differ"
        + (f", {len(table.live_errors)} could not be asked" if table.live_errors else "")
    ]
    if differs:
        shown = [f"{g.label}: held {g.held:,}, source {g.expected:,}" for g in differs]
        if len(shown) > MAX_MISSING_ITEMS:
            shown = [*shown[:MAX_MISSING_ITEMS], f"... and {len(shown) - MAX_MISSING_ITEMS} more"]
        lines.append("    live differs: " + "; ".join(shown))
    if table.live_errors:
        lines.append("    live errors: " + "; ".join(table.live_errors[:5]))
    return lines


def _is_label(name: str) -> bool:
    """A dataset whose name is a label (a manifest file or a derived check), not a table."""
    return name.startswith("downloads/") or name == SCHEDULE_SETTLED_LABEL


def _holds_no_rows(table: TableReport) -> bool:
    """Known empty or absent; a `--light` report that skipped the count says nothing."""
    return table.rows == 0 or table.status in ("table_absent", "empty")


def _table_text(table: TableReport) -> list[str]:
    if _is_label(table.table):
        rows = "local file" if table.table.startswith("downloads/") else "derived from other tables"
    else:
        rows = (
            "table absent"
            if table.status == "table_absent"
            else "row count skipped"
            if table.rows is None
            else f"{table.rows:,} rows"
        )
    if table.status == "no_expectation":
        return [f"  {table.table}: no expectation defined: {table.expectation} ({rows})"]
    lines = [f"  {table.table} [{table.unit}]: {STATUS_LABEL[table.status]} ({rows})"]
    lines.append(f"    expectation: {table.expectation}")
    if table.first_date:
        unparsed = f"; {table.date_not_parsed:,} values not a date" if table.date_not_parsed else ""
        lines.append(
            f"    dates ({table.date_column}): {table.first_date} to {table.last_date}{unparsed}"
        )
    if table.groups:
        lines.append(
            f"    expected {table.expected:,} | held {table.held:,} | "
            f"accounted-for (source gaps) {table.accounted:,} | missing {table.missing:,}"
        )
    if table.missing:
        lines.append(f"    missing: {missing_text(table)}")
    lines += _live_text(table)
    if table.fix:
        lines.append(f"    fix: {table.fix}")
    if table.caveat and table.status != "complete":
        lines.append(f"    note: {table.caveat}")
    return lines


def _summary(tables: list[TableReport]) -> str:
    with_expectation = sum(1 for t in tables if t.status != "no_expectation")
    return f"{with_expectation} with an expectation, {len(tables) - with_expectation} without"


def render_text(report: Report) -> str:
    lines: list[str] = []
    for source, tables in _by_source(report).items():
        lines.append(f"== {source}: {len(tables)} tables, {_summary(tables)} ==")
        if all(_holds_no_rows(t) for t in tables if not _is_label(t.table)):
            lines.append("  source holds no rows in any table")
        for table in tables:
            lines += _table_text(table)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n" if lines else "nothing to report\n"


def render_markdown(report: Report) -> str:
    lines = [
        "# Coverage",
        "",
        "What each source should hold versus what the database holds. Generated by "
        "`mlb coverage --markdown`; read-only.",
        "",
    ]
    for source, tables in _by_source(report).items():
        lines += [
            f"## {source}",
            "",
            f"{len(tables)} tables, {_summary(tables)}.",
            "",
            "| table | unit | status | expected | held | accounted | missing | dates | fix |",
            "|---|---|---|---:|---:|---:|---:|---|---|",
        ]
        for t in tables:
            fix = f"`{t.fix}`" if t.fix else ""
            dates = f"{t.first_date} to {t.last_date}" if t.first_date else ""
            counts = (
                f"{t.expected} | {t.held} | {t.accounted} | {t.missing}"
                if t.groups
                else " |  |  | "
            )
            status = STATUS_LABEL[t.status]
            lines.append(f"| `{t.table}` | {t.unit} | {status} | {counts} | {dates} | {fix} |")
        lines.append("")
        for t in tables:
            if t.status == "no_expectation":
                lines.append(f"- `{t.table}`: no expectation defined: {t.expectation}")
            elif t.missing:
                lines.append(f"- `{t.table}` missing: {missing_text(t)}")
            lines += [f"- `{t.table}` {line.strip()}" for line in _live_text(t)]
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_json(report: Report) -> str:
    sources = []
    for source, tables in _by_source(report).items():
        sources.append(
            {
                "source": source,
                "tables": [
                    {
                        "table": t.table,
                        "unit": t.unit,
                        "status": t.status,
                        "expectation": t.expectation,
                        "rows": t.rows,
                        "expected": t.expected,
                        "held": t.held,
                        "accounted": t.accounted,
                        "missing": t.missing,
                        "groups": [
                            {
                                "group": g.label,
                                "expected": g.expected,
                                "held": g.held,
                                "accounted": g.accounted,
                                "missing": g.missing,
                            }
                            for g in t.groups
                        ],
                        "missing_groups": [
                            {"group": g.label, "missing": g.missing}
                            for g in t.groups
                            if g.missing > 0
                        ],
                        "fix": t.fix,
                        "caveat": t.caveat,
                        "date_column": t.date_column or None,
                        "first_date": t.first_date,
                        "last_date": t.last_date,
                        "date_not_parsed": t.date_not_parsed,
                        "live": [
                            {"group": g.label, "source": g.expected, "held": g.held} for g in t.live
                        ],
                        "live_errors": t.live_errors,
                    }
                    for t in tables
                ],
            }
        )
    return json.dumps({"sources": sources}, indent=2, sort_keys=True)
