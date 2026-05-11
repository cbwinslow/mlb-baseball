"""Ingest CLI Commands

Name:    ingest.py
Date:    2026-05-11
Version: 1.0.0

Description:
    Commands to parse and insert downloaded raw data into staging/core tables.

Note:
    Full DB wiring is tracked in Phase 2.
    The ingestors exist in baseball/sources/*/ingestor.py but the
    database insertion stubs (TODO comments) are not yet connected.
    These commands scaffold the interface so the CLI is fully defined.
"""

import typer
from rich.console import Console

from baseball.core.logging import get_logger

logger = get_logger(__name__)
console = Console()

app = typer.Typer(
    name="ingest",
    help="Ingest downloaded data into the database.",
    no_args_is_help=True,
)


@app.command()
def retrosheet(
    season: int = typer.Option(..., help="Season to ingest"),
    ingest_type: str = typer.Option(
        "all", "--type", help="Type: all, events, rosters, schedules"
    ),
) -> None:
    """Ingest Retrosheet event/roster/schedule data into the database.

    Requires:
        - Raw files downloaded via: baseball download retrosheet --season YEAR
        - DATABASE_URL environment variable set

    Examples:
        baseball ingest retrosheet --season 2024
        baseball ingest retrosheet --season 2024 --type events
    """
    console.print(f"[cyan]Ingesting Retrosheet data for {season} (type={ingest_type})[/cyan]")
    # TODO(phase2): wire to baseball.sources.retrosheet.ingestor.RetroIngestor
    # The ingestor is implemented but database insert at ingestor.py:62 is TODO
    console.print(
        "[yellow]⚠ Retrosheet ingest DB wiring not yet complete. "
        "Tracked in Phase 2.[/yellow]"
    )
    raise typer.Exit(code=1)


@app.command()
def mlbstatsapi(
    season: int = typer.Option(..., help="Season to ingest"),
) -> None:
    """Ingest MLB StatsAPI data into the database.

    Requires:
        - Raw files downloaded via: baseball download mlbstatsapi --season YEAR
        - DATABASE_URL environment variable set

    Examples:
        baseball ingest mlbstatsapi --season 2024
    """
    console.print(f"[cyan]Ingesting MLB StatsAPI data for {season}[/cyan]")
    # TODO(phase2): MLBIngestor module does not yet exist
    # Per review: baseball/sources/mlb/ingestor.py needs to be created
    console.print(
        "[yellow]⚠ MLB StatsAPI ingestor not yet implemented. "
        "Tracked in Phase 2.[/yellow]"
    )
    raise typer.Exit(code=1)


@app.command()
def statcast(
    start_date: str = typer.Option(..., help="Start date YYYY-MM-DD"),
    end_date: str = typer.Option(None, help="End date YYYY-MM-DD"),
) -> None:
    """Ingest StatCast pitch data into the database.

    Requires:
        - Raw files downloaded via: baseball download statcast --start-date DATE
        - DATABASE_URL environment variable set

    Examples:
        baseball ingest statcast --start-date 2024-04-01 --end-date 2024-10-01
    """
    end = end_date or start_date
    console.print(f"[cyan]Ingesting StatCast data from {start_date} to {end}[/cyan]")
    # TODO(phase2): wire to baseball.sources.statcast.ingestor.StatcastIngestor
    # The ingestor is implemented but database insert at ingestor.py:56 is TODO
    console.print(
        "[yellow]⚠ StatCast ingest DB wiring not yet complete. "
        "Tracked in Phase 2.[/yellow]"
    )
    raise typer.Exit(code=1)
