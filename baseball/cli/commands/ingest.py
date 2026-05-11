"""Ingest CLI Commands

Name:    ingest.py
Date:    2026-05-11
Version: 1.0.0

Description:
    Commands to parse and insert downloaded raw data into staging/core tables.
"""

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from baseball.core.logging import get_logger
from baseball.sources.retrosheet.ingestor import RetroEventFileIngestor

logger = get_logger(__name__)
console = Console()

app = typer.Typer(
    name="ingest",
    help="Ingest downloaded data into the database.",
    no_args_is_help=True,
)


def _print_ingest_result(title: str, result) -> None:
    """Render an IngestResult as a rich table."""
    console.print(f"[bold cyan]{title}[/bold cyan]")
    table = Table(show_header=False)
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="white")
    table.add_row("Status", str(result.status))
    table.add_row("Rows Inserted", str(getattr(result, "rows_inserted", "-")))
    table.add_row("Rows Skipped", str(getattr(result, "rows_skipped", "-")))
    table.add_row("Rows Failed", str(getattr(result, "rows_failed", "-")))
    table.add_row("Started", str(result.start_time))
    table.add_row("Ended", str(result.end_time))
    if getattr(result, "error", None):
        table.add_row("Error", result.error)
    console.print(table)


@app.command()
def mlbstatsapi(
    season: int = typer.Option(..., help="Season to ingest"),
    data_dir: Path = typer.Option(
        Path("data/raw/mlb"),
        "--data-dir",
        help="Directory containing downloaded MLB raw files",
    ),
) -> None:
    """Ingest MLB StatsAPI data into the database.

    Examples:
        baseball ingest mlbstatsapi --season 2024
    """
    # MLB ingestor is not yet implemented; placeholder until MLB ingestor.py exists.
    console.print(
        f"[yellow]MLB StatsAPI ingest not yet implemented (season={season}, "
        f"data_dir={data_dir})[/yellow]"
    )
    console.print(
        "[dim]Create baseball/sources/mlb/ingestor.py to wire this command.[/dim]"
    )


@app.command()
def retrosheet(
    season: int = typer.Option(..., help="Season to ingest"),
    ingest_type: str = typer.Option(
        "all", "--type", help="Type: all, events, gamelogs"
    ),
    data_dir: Path = typer.Option(
        Path("data/raw/retrosheet"),
        "--data-dir",
        help="Directory containing downloaded Retrosheet files",
    ),
    db_url: str = typer.Option(
        None,
        "--db-url",
        envvar="DATABASE_URL",
        help="Database connection URL (or set DATABASE_URL env var)",
    ),
) -> None:
    """Ingest Retrosheet event/gamelog data into the database.

    Examples:
        baseball ingest retrosheet --season 2024
        baseball ingest retrosheet --season 2024 --type events
    """
    try:
        ingestor = RetroEventFileIngestor(db_connection=db_url)

        if ingest_type in ("events", "all"):
            event_files = sorted(data_dir.glob(f"*{season}*.ev?"))
            if not event_files:
                console.print(
                    f"[yellow]No event files found in {data_dir} for season {season}. "
                    f"Run: baseball download retrosheet --season {season}[/yellow]"
                )
            for ef in event_files:
                result = ingestor.ingest_event_file(path=ef, season=season)
                _print_ingest_result(f"Retrosheet event file: {ef.name}", result)

        if ingest_type in ("gamelogs", "all"):
            for league in ("AL", "NL"):
                gl_files = sorted(
                    data_dir.glob(f"GL{season}*{league}*.txt")
                ) or sorted(data_dir.glob(f"GL{season}*.txt"))
                if not gl_files:
                    console.print(
                        f"[yellow]No gamelog files found for {season} {league}[/yellow]"
                    )
                    continue
                for gf in gl_files:
                    result = ingestor.ingest_game_logs(
                        path=gf, season=season, league=league
                    )
                    _print_ingest_result(
                        f"Retrosheet gamelogs: {gf.name} ({league})", result
                    )
    except Exception as exc:
        logger.exception("Retrosheet ingest failed: %s", exc)
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc


@app.command()
def statcast(
    start_date: str = typer.Option(..., help="Start date YYYY-MM-DD"),
    end_date: str = typer.Option(None, help="End date YYYY-MM-DD"),
    season: int = typer.Option(None, help="Full season shortcut"),
) -> None:
    """Ingest StatCast pitch data into the database.

    Examples:
        baseball ingest statcast --season 2024
        baseball ingest statcast --start-date 2024-04-01 --end-date 2024-10-01
    """
    console.print(
        "[yellow]StatCast ingest not yet implemented[/yellow]"
    )
    console.print(
        "[dim]Create baseball/sources/statcast/ingestor.py to wire this command.[/dim]"
    )
