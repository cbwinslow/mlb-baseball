"""
================================================================================
Ingest Commands
Date: 2026-05-09

CLI commands for ingesting downloaded data.
================================================================================
"""

from pathlib import Path

import typer
from rich.console import Console

from baseball.sources.mlb.ingestor import MLBIngestor
from baseball.sources.retrosheet.ingestor import RetroEventFileIngestor
from baseball.sources.statcast.ingestor import StatcastIngestor

app = typer.Typer(help="Ingest downloaded data into database")
console = Console()


# MLB Ingest Commands
@app.command()
def mlb_schedule(
    path: Path = typer.Option(..., "--path", "-p", help="Path to schedule CSV"),
) -> None:
    """Ingest MLB schedule into database."""
    console.print(f"[blue]Ingesting {path}...[/blue]")
    ingestor = MLBIngestor()
    result = ingestor.ingest_schedule(path)

    if result.success:
        console.print(
            f"[green]✓[/green] Ingested {result.rows_inserted} rows "
            f"in {result.duration_seconds:.2f}s"
        )
    else:
        console.print(f"[red]✗[/red] {result.error}")
        raise typer.Exit(code=1)


@app.command()
def mlb_game(
    path: Path = typer.Option(..., "--path", "-p", help="Path to game JSON"),
    game_pk: int = typer.Option(..., "--game-pk", help="Game ID"),
) -> None:
    """Ingest MLB game data into database."""
    console.print(f"[blue]Ingesting game {game_pk}...[/blue]")
    ingestor = MLBIngestor()
    result = ingestor.ingest_game(path, game_pk=game_pk)

    if result.success:
        console.print(f"[green]✓[/green] Ingested in {result.duration_seconds:.2f}s")
    else:
        console.print(f"[red]✗[/red] {result.error}")
        raise typer.Exit(code=1)


# Retrosheet Ingest Commands
@app.command()
def retrosheet_events(
    path: Path = typer.Option(..., "--path", "-p", help="Path to event file"),
    season: int = typer.Option(..., "--season", "-s", help="Season year"),
) -> None:
    """Ingest Retrosheet events into database."""
    console.print(f"[blue]Ingesting {path}...[/blue]")
    ingestor = RetroEventFileIngestor()
    result = ingestor.ingest_event_file(path, season=season)

    if result.success:
        console.print(
            f"[green]✓[/green] Ingested {result.rows_inserted} events "
            f"in {result.duration_seconds:.2f}s"
        )
    else:
        console.print(f"[red]✗[/red] {result.error}")
        raise typer.Exit(code=1)


@app.command()
def retrosheet_game_logs(
    path: Path = typer.Option(..., "--path", "-p", help="Path to game logs file"),
    season: int = typer.Option(..., "--season", "-s", help="Season year"),
    league: str = typer.Option("AL", "--league", "-l", help="AL or NL"),
) -> None:
    """Ingest Retrosheet game logs into database."""
    console.print(f"[blue]Ingesting {path}...[/blue]")
    ingestor = RetroEventFileIngestor()
    result = ingestor.ingest_game_logs(path, season=season, league=league)

    if result.success:
        console.print(
            f"[green]✓[/green] Ingested {result.rows_inserted} records "
            f"in {result.duration_seconds:.2f}s"
        )
    else:
        console.print(f"[red]✗[/red] {result.error}")
        raise typer.Exit(code=1)


# StatCast Ingest Command
@app.command()
def statcast(
    path: Path = typer.Option(..., "--path", "-p", help="Path to StatCast CSV"),
) -> None:
    """Ingest StatCast pitch data into database."""
    console.print(f"[blue]Ingesting {path}...[/blue]")
    ingestor = StatcastIngestor()
    result = ingestor.ingest_pitch_data(path)

    if result.success:
        console.print(
            f"[green]✓[/green] Ingested {result.rows_inserted} pitches "
            f"in {result.duration_seconds:.2f}s"
        )
    else:
        console.print(f"[red]✗[/red] {result.error}")
        raise typer.Exit(code=1)
