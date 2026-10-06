"""`mlb coverage`: what each source should hold versus what the database holds.

Read-only. See ``AGENTS.md`` in this directory for the contract.
"""

from mlb_baseball.coverage.engine import Report, TableReport, collect
from mlb_baseball.coverage.registry import DATASETS
from mlb_baseball.coverage.render import render_json, render_markdown, render_text

__all__ = [
    "DATASETS",
    "Report",
    "TableReport",
    "collect",
    "render_json",
    "render_markdown",
    "render_text",
    "run",
]


def run(
    *,
    source: str | None,
    table: str | None,
    as_json: bool,
    as_markdown: bool,
    missing_only: bool = False,
) -> bool:
    """Print the report; return True when any table in it has a gap (checked before
    ``missing_only`` hides the clean tables)."""
    report = collect(source=source, table=table)
    has_gap = report.has_gap
    if missing_only:
        report = report.only_gaps()
    if as_json:
        print(render_json(report))
    elif as_markdown:
        print(render_markdown(report), end="")
    else:
        print(render_text(report), end="")
    return has_gap
