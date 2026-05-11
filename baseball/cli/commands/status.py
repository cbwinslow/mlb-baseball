"""Status CLI Commands

Name:    status.py
Date:    2026-05-11
Version: 1.0.0

Description:
    Commands to report system health, data freshness, and pipeline coverage.

Note:
    Full implementation is tracked in Phase 2 once DB ingest wiring is complete.
"""

import os

import typer
from rich.console import Console
from rich.table import Table

from baseball.core.logging import get_logger

logger = get_logger(__name__)
console = Console()

app = typer.Typer(
    name="status",
    help="Report system and data status.",
    no_args_is_help=True,
)


@app.command()
def system() -> None:
    """Show system health: DB connectivity, environment, dependencies.

    Examples:
        baseball status system
    """
    console.print("[bold cyan]System Status[/bold cyan]")

    # Check DATABASE_URL
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        # Mask credentials for display
        try:
            from urllib.parse import urlparse

            parsed = urlparse(db_url)
            safe_url = db_url.replace(parsed.password or "", "***") if parsed.password else db_url
        except Exception:
            safe_url = "(set)"
        console.print(f"  DATABASE_URL : [green]{safe_url}[/green]")
    else:
        console.print("  DATABASE_URL : [red]NOT SET[/red]")

    data_dir = os.getenv("DATA_DIR", "(not set)")
    console.print(f"  DATA_DIR     : [cyan]{data_dir}[/cyan]")

    log_level = os.getenv("LOG_LEVEL", "INFO")
    console.print(f"  LOG_LEVEL    : [cyan]{log_level}[/cyan]")

    # TODO(phase2): attempt DB connection and report pool status
    if db_url:
        console.print(
            "\n[yellow]⚠ Live DB health check not yet wired. "
            "Use `baseball db status` for full DB diagnostics.[/yellow]"
        )


@app.command()
def data(
    season: int = typer.Option(None, help="Specific season to check (default: current)"),
) -> None:
    """Show data coverage and freshness by source and season.

    Examples:
        baseball status data
        baseball status data --season 2024
    """
    season_label = str(season) if season else "all seasons"
    console.print(f"[bold cyan]Data Coverage — {season_label}[/bold cyan]")

    table = Table(title="Source Coverage", show_header=True)
    table.add_column("Source", style="cyan")
    table.add_column("Status", style="magenta")
    table.add_column("Notes")

    sources = [
        ("MLB StatsAPI", "[yellow]Pending[/yellow]", "Ingest not yet wired (Phase 2)"),
        ("Retrosheet", "[yellow]Pending[/yellow]", "Ingest not yet wired (Phase 2)"),
        ("StatCast", "[yellow]Pending[/yellow]", "Ingest not yet wired (Phase 2)"),
        ("FanGraphs", "[yellow]Pending[/yellow]", "Ingest not yet wired (Phase 2)"),
        ("Lahman", "[yellow]Pending[/yellow]", "Ingest not yet wired (Phase 2)"),
        ("ESPN", "[yellow]Pending[/yellow]", "Ingest not yet wired (Phase 2)"),
        ("Weather", "[yellow]Pending[/yellow]", "Ingest not yet wired (Phase 2)"),
    ]

    for source, status, notes in sources:
        table.add_row(source, status, notes)

    console.print(table)
    # TODO(phase2): query core tables for actual row counts and freshness timestamps
