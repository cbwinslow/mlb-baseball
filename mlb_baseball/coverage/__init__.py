"""`mlb coverage`: what each source should hold versus what the database holds.

Read-only. See ``AGENTS.md`` in this directory for the contract.
"""

from mlb_baseball.coverage.engine import (
    AcceptedGap,
    Report,
    TableReport,
    collect,
    load_accepted_gaps,
)
from mlb_baseball.coverage.registry import DATASETS
from mlb_baseball.coverage.render import render_json, render_markdown, render_text

__all__ = [
    "AcceptedGap",
    "DATASETS",
    "Report",
    "TableReport",
    "collect",
    "load_accepted_gaps",
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
    probe: bool = False,
    unexplained_only: bool = False,
    light: bool = False,
) -> bool:
    """Print the report; return True when any table in it has a gap (checked before
    ``missing_only`` hides the clean tables). With ``unexplained_only`` only tables with a gap not
    listed in ``accepted_gaps.toml`` (up to its ceiling) are reported and counted."""
    report = collect(source=source, table=table, probe=probe, light=light)
    has_gap = report.has_gap
    if unexplained_only:
        report = report.unexplained(load_accepted_gaps())
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
