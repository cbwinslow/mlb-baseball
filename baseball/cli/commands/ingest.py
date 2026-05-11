"""Ingest CLI Commands

Name:    ingest.py
Date:    2026-05-11
Version: 1.1.0

Description:
    Commands to parse and insert downloaded raw data into staging/core tables.
"""

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from baseball.core.logging import get_logger
from baseball.sources.mlb.ingestor import MLBIngestor
from baseball.sources.retrosheet.ingestor import RetroEventFileIngestor
from baseball.sources.statcast.ingestor import StatcastIngestor

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
    db_url: str = typer.Option(
        None,
        "--db-url",
        envvar="DATABASE_URL",
        help="Database connection URL (or set DATABASE_URL env var)",
    ),
) -> None:
    """Ingest MLB StatsAPI data into the database.

    Examples:
        baseball ingest mlbstatsapi --season 2024
    """
    try:
        ingestor = MLBIngestor(db_connection=db_url)

        # Ingest schedule CSV
        schedule_files = sorted(data_dir.glob(f"mlb_schedule_{season}*.csv"))
        if not schedule_files:
            # Fallback: any CSV in the dir for that season
            schedule_files = sorted(data_dir.glob(f"*{season}*.csv"))
        if not schedule_files:
            console.print(
                f"[yellow]No schedule CSV files found in {data_dir} for season {season}.\n"
                f"Run: baseball download mlbstatsapi --season {season}[/yellow]"
            )
        for sf in schedule_files:
            result = ingestor.ingest_schedule(path=sf, season=season)
            _print_ingest_result(f"MLB schedule: {sf.name}", result)

        # Ingest game JSON files
        game_files = sorted(data_dir.glob(f"*{season}*/game_*.json")) or sorted(
            data_dir.glob(f"game_*.json")
        )
        for gf in game_files:
            game_pk = int(gf.stem.replace("game_", "")) if gf.stem.startswith("game_") else 0
            result = ingestor.ingest_game(path=gf, game_pk=game_pk, season=season)
            _print_ingest_result(f"MLB game: {gf.name}", result)

    except Exception as exc:
        logger.exception("MLB StatsAPI ingest failed: %s", exc)
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc


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
    season: int = typer.Option(None, help="Full season shortcut (overrides date range)"),
    data_dir: Path = typer.Option(
        Path("data/raw/statcast"),
        "--data-dir",
        help="Directory containing downloaded StatCast files",
    ),
    db_url: str = typer.Option(
        None,
        "--db-url",
        envvar="DATABASE_URL",
        help="Database connection URL (or set DATABASE_URL env var)",
    ),
) -> None:
    """Ingest StatCast pitch data into the database.

    Examples:
        baseball ingest statcast --season 2024
        baseball ingest statcast --start-date 2024-04-01 --end-date 2024-10-01
    """
    try:
        ingestor = StatcastIngestor(db_connection=db_url)
        target_season = season or int(start_date[:4])

        csv_files = sorted(data_dir.glob(f"statcast_{target_season}*.csv")) or sorted(
            data_dir.glob(f"*{target_season}*.csv")
        )
        if not csv_files:
            console.print(
                f"[yellow]No StatCast CSV files found in {data_dir} for season {target_season}.\n"
                f"Run: baseball download statcast --season {target_season}[/yellow]"
            )
            return

        for cf in csv_files:
            result = ingestor.ingest_season(path=cf, season=target_season)
            _print_ingest_result(f"StatCast: {cf.name}", result)

    except Exception as exc:
        logger.exception("StatCast ingest failed: %s", exc)
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc
