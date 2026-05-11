"""Download CLI Commands

Name:    download.py
Date:    2026-05-11
Version: 1.0.0

Description:
    Commands to fetch data from MLB StatsAPI, Retrosheet, StatCast,
    FanGraphs, Lahman, ESPN, and Weather sources.
"""

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from baseball.core.enums import ResultStatus
from baseball.core.logging import get_logger
from baseball.sources.mlb.downloader import MLBDownloader
from baseball.sources.retrosheet.downloader import RetroEventFileDownloader
from baseball.sources.statcast.downloader import StatcastDownloader

logger = get_logger(__name__)
console = Console()

app = typer.Typer(
    name="download",
    help="Download raw data from external sources.",
    no_args_is_help=True,
)


def _print_result(title: str, result) -> None:
    """Render a DownloadResult as a rich table."""
    console.print(f"[bold cyan]{title}[/bold cyan]")
    table = Table(show_header=False)
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="white")
    table.add_row("Status", str(result.status))
    table.add_row("Rows", str(getattr(result, "rows_downloaded", "-")))
    table.add_row("Bytes", str(getattr(result, "bytes_downloaded", "-")))
    table.add_row("Started", str(result.start_time))
    table.add_row("Ended", str(result.end_time))
    files = getattr(result, "files_downloaded", [])
    table.add_row("Files", ", ".join(str(f) for f in files) if files else "-")
    if getattr(result, "error", None):
        table.add_row("Error", result.error)
    if getattr(result, "error_code", None):
        table.add_row("Error Code", result.error_code)
    console.print(table)


@app.command()
def mlbstatsapi(
    season: int = typer.Option(..., help="Season to download"),
    game_pk: int = typer.Option(None, help="Specific game PK to download"),
    output_dir: Path = typer.Option(
        Path("data/raw/mlb"),
        "--output-dir",
        help="Directory for downloaded MLB raw files",
    ),
    rate_limit: float = typer.Option(
        0.5,
        "--rate-limit",
        min=0.0,
        help="Minimum seconds between MLB API requests",
    ),
) -> None:
    """Download data from MLB StatsAPI.

    Examples:
        baseball download mlbstatsapi --season 2024
        baseball download mlbstatsapi --season 2024 --game-pk 123456
    """
    try:
        downloader = MLBDownloader(output_dir=output_dir, rate_limit=rate_limit)
        if game_pk is not None:
            result = downloader.download_game(game_pk=game_pk)
            _print_result(f"MLB StatsAPI game download: {game_pk}", result)
        else:
            result = downloader.download_schedule(season=season)
            _print_result(f"MLB StatsAPI schedule download: season {season}", result)
        if result.status != ResultStatus.SUCCESS:
            raise typer.Exit(code=1)
    except typer.Exit:
        raise
    except Exception as exc:
        logger.exception("MLB StatsAPI download failed: %s", exc)
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc


@app.command()
def retrosheet(
    season: int = typer.Option(..., help="Season to download"),
    download_type: str = typer.Option(
        "all", "--type", help="Type: all, events, gamelogs"
    ),
    output_dir: Path = typer.Option(
        Path("data/raw/retrosheet"),
        "--output-dir",
        help="Directory for downloaded Retrosheet files",
    ),
) -> None:
    """Download event and gamelog files from Retrosheet.

    Examples:
        baseball download retrosheet --season 2024
        baseball download retrosheet --season 2024 --type events
    """
    try:
        downloader = RetroEventFileDownloader(output_dir=output_dir)
        if download_type in ("events", "all"):
            result = downloader.download_event_files(season=season)
            _print_result(f"Retrosheet events download: season {season}", result)
            if result.status != ResultStatus.SUCCESS:
                raise typer.Exit(code=1)
        if download_type in ("gamelogs", "all"):
            for league in ("AL", "NL"):
                result = downloader.download_game_logs(season=season, league=league)
                _print_result(
                    f"Retrosheet game logs download: {season} {league}", result
                )
                if result.status != ResultStatus.SUCCESS:
                    raise typer.Exit(code=1)
    except typer.Exit:
        raise
    except Exception as exc:
        logger.exception("Retrosheet download failed: %s", exc)
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc


@app.command()
def statcast(
    start_date: str = typer.Option(..., help="Start date YYYY-MM-DD"),
    end_date: str = typer.Option(None, help="End date YYYY-MM-DD (defaults to start_date)"),
    season: int = typer.Option(None, help="Full season shortcut (overrides date range)"),
    output_dir: Path = typer.Option(
        Path("data/raw/statcast"),
        "--output-dir",
        help="Directory for downloaded StatCast files",
    ),
) -> None:
    """Download Statcast pitch data from Baseball Savant via pybaseball.

    Examples:
        baseball download statcast --season 2024
        baseball download statcast --start-date 2024-04-01 --end-date 2024-10-01
    """
    try:
        downloader = StatcastDownloader(output_dir=output_dir)
        if season is not None:
            result = downloader.download_season(season=season)
            _print_result(f"StatCast season download: {season}", result)
        else:
            if start_date is None:
                console.print("[red]Error:[/red] --start-date is required when --season is not provided")
                raise typer.Exit(code=1)
            # StatcastDownloader.download_season is the primary method;
            # for date-range use, derive season from start_date year.
            derived_season = int(start_date[:4])
            console.print(
                f"[yellow]Note:[/yellow] date-range filtering not yet supported; "
                f"downloading full season {derived_season}"
            )
            result = downloader.download_season(season=derived_season)
            _print_result(f"StatCast season download: {derived_season}", result)
        if result.status != ResultStatus.SUCCESS:
            raise typer.Exit(code=1)
    except typer.Exit:
        raise
    except Exception as exc:
        logger.exception("StatCast download failed: %s", exc)
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc


@app.command()
def fangraphs(
    season: int = typer.Option(..., help="Season to download"),
) -> None:
    """Download FanGraphs data."""
    console.print(f"[yellow]FanGraphs download not yet implemented (season={season})[/yellow]")


@app.command()
def lahman(
    season: int = typer.Option(None, help="Season to download (omit for full database)"),
) -> None:
    """Download Lahman database."""
    console.print("[yellow]Lahman download not yet implemented[/yellow]")
