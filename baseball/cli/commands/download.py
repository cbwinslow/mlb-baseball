
"""
================================================================================
Download Commands
Date: 2026-05-09

CLI commands for downloading baseball data.
================================================================================
"""

import typer
from pathlib import Path
from typing import Optional
from rich.console import Console

from baseball.services.downloads import (
    download_mlb_season,
    download_mlb_game,
    download_retrosheet_events,
    download_retrosheet_game_logs,
    download_statcast_season,
    download_statcast_pitcher,
    download_statcast_batter,
    download_lahman,
    download_fangraphs_batting,
    download_fangraphs_pitching,
    download_espn_scoreboard,
    download_weather_forecast,
)


app = typer.Typer(help='Download baseball data from various sources')
console = Console()


# MLB Commands
@app.command()
def mlb_schedule(
    season: int = typer.Option(..., '--season', '-s', help='Season year'),
    team_id: Optional[str] = typer.Option(None, '--team', '-t', help='Team ID'),
    output_dir: Path = typer.Option(Path('data/raw/mlb'), '--output', '-o'),
) -> None:
    """Download MLB schedule."""
    console.print(f'[blue]Downloading MLB schedule for {season}...[/blue]')
    result = download_mlb_season(season=season, team_id=team_id, output_dir=output_dir)

    if result.success:
        console.print(
            f'[green]✓[/green] Downloaded {result.rows_downloaded} games '
            f'in {result.duration_seconds:.2f}s'
        )
    else:
        console.print(f'[red]✗[/red] {result.error}')
        raise typer.Exit(code=1)


@app.command()
def mlb_game(
    game_pk: int = typer.Option(..., '--game-pk', help='Game ID'),
    output_dir: Path = typer.Option(Path('data/raw/mlb'), '--output', '-o'),
) -> None:
    """Download MLB game data."""
    console.print(f'[blue]Downloading game {game_pk}...[/blue]')
    result = download_mlb_game(game_pk=game_pk, output_dir=output_dir)

    if result.success:
        console.print(
            f'[green]✓[/green] Downloaded {len(result.files_downloaded)} files '
            f'in {result.duration_seconds:.2f}s'
        )
    else:
        console.print(f'[red]✗[/red] {result.error}')
        raise typer.Exit(code=1)


# Retrosheet Commands
@app.command()
def retrosheet_events(
    season: int = typer.Option(..., '--season', '-s', help='Season year'),
    teams: Optional[list[str]] = typer.Option(None, '--teams', '-t', help='Team codes'),
    output_dir: Path = typer.Option(Path('data/raw/retrosheet'), '--output', '-o'),
) -> None:
    """Download Retrosheet event files."""
    console.print(f'[blue]Downloading Retrosheet events for {season}...[/blue]')
    result = download_retrosheet_events(season=season, teams=teams, output_dir=output_dir)

    if result.success:
        console.print(
            f'[green]✓[/green] Extracted {result.rows_downloaded} files '
            f'in {result.duration_seconds:.2f}s'
        )
    else:
        console.print(f'[red]✗[/red] {result.error}')
        raise typer.Exit(code=1)


@app.command()
def retrosheet_game_logs(
    season: int = typer.Option(..., '--season', '-s', help='Season year'),
    league: str = typer.Option('AL', '--league', '-l', help='AL or NL'),
    output_dir: Path = typer.Option(Path('data/raw/retrosheet'), '--output', '-o'),
) -> None:
    """Download Retrosheet game logs."""
    console.print(f'[blue]Downloading {league} game logs for {season}...[/blue]')
    result = download_retrosheet_game_logs(season=season, league=league, output_dir=output_dir)

    if result.success:
        console.print(
            f'[green]✓[/green] Downloaded {result.rows_downloaded} records '
            f'in {result.duration_seconds:.2f}s'
        )
    else:
        console.print(f'[red]✗[/red] {result.error}')
        raise typer.Exit(code=1)


# StatCast Commands
@app.command()
def statcast_season(
    season: int = typer.Option(..., '--season', '-s', help='Season year'),
    output_dir: Path = typer.Option(Path('data/raw/statcast'), '--output', '-o'),
) -> None:
    """Download StatCast data for season."""
    console.print(f'[blue]Downloading StatCast for {season}...[/blue]')
    result = download_statcast_season(season=season, output_dir=output_dir)

    if result.success:
        console.print(
            f'[green]✓[/green] Downloaded {result.rows_downloaded:,} pitches '
            f'in {result.duration_seconds:.2f}s'
        )
    else:
        console.print(f'[red]✗[/red] {result.error}')
        raise typer.Exit(code=1)


@app.command()
def statcast_pitcher(
    pitcher_id: int = typer.Option(..., '--pitcher-id', help='Pitcher MLBAM ID'),
    season: Optional[int] = typer.Option(None, '--season', '-s', help='Season'),
    output_dir: Path = typer.Option(Path('data/raw/statcast'), '--output', '-o'),
) -> None:
    """Download StatCast data for pitcher."""
    console.print(f'[blue]Downloading StatCast for pitcher {pitcher_id}...[/blue]')
    result = download_statcast_pitcher(pitcher_id=pitcher_id, season=season, output_dir=output_dir)

    if result.success:
        console.print(
            f'[green]✓[/green] Downloaded {result.rows_downloaded:,} pitches '
            f'in {result.duration_seconds:.2f}s'
        )
    else:
        console.print(f'[red]✗[/red] {result.error}')
        raise typer.Exit(code=1)


@app.command()
def statcast_batter(
    batter_id: int = typer.Option(..., '--batter-id', help='Batter MLBAM ID'),
    season: Optional[int] = typer.Option(None, '--season', '-s', help='Season'),
    output_dir: Path = typer.Option(Path('data/raw/statcast'), '--output', '-o'),
) -> None:
    """Download StatCast data for batter."""
    console.print(f'[blue]Downloading StatCast for batter {batter_id}...[/blue]')
    result = download_statcast_batter(batter_id=batter_id, season=season, output_dir=output_dir)

    if result.success:
        console.print(
            f'[green]✓[/green] Downloaded {result.rows_downloaded:,} pitches '
            f'in {result.duration_seconds:.2f}s'
        )
    else:
        console.print(f'[red]✗[/red] {result.error}')
        raise typer.Exit(code=1)


# Lahman Command
@app.command()
def lahman(
    tables: Optional[list[str]] = typer.Option(
        None, '--tables', '-t', help='Tables to download'
    ),
    output_dir: Path = typer.Option(Path('data/raw/lahman'), '--output', '-o'),
) -> None:
    """Download Lahman database."""
    console.print('[blue]Downloading Lahman database...[/blue]')
    result = download_lahman(tables=tables, output_dir=output_dir)

    if result.success:
        console.print(
            f'[green]✓[/green] Extracted {len(result.files_downloaded)} files '
            f'in {result.duration_seconds:.2f}s'
        )
    else:
        console.print(f'[red]✗[/red] {result.error}')
        raise typer.Exit(code=1)


# FanGraphs Commands
@app.command()
def fangraphs_batting(
    season: int = typer.Option(..., '--season', '-s', help='Season year'),
    output_dir: Path = typer.Option(Path('data/raw/fangraphs'), '--output', '-o'),
) -> None:
    """Download FanGraphs batting stats."""
    console.print(f'[blue]Downloading FanGraphs batting for {season}...[/blue]')
    result = download_fangraphs_batting(season=season, output_dir=output_dir)

    if result.success:
        console.print(
            f'[green]✓[/green] Downloaded {result.rows_downloaded} records '
            f'in {result.duration_seconds:.2f}s'
        )
    else:
        console.print(f'[red]✗[/red] {result.error}')
        raise typer.Exit(code=1)


@app.command()
def fangraphs_pitching(
    season: int = typer.Option(..., '--season', '-s', help='Season year'),
    output_dir: Path = typer.Option(Path('data/raw/fangraphs'), '--output', '-o'),
) -> None:
    """Download FanGraphs pitching stats."""
    console.print(f'[blue]Downloading FanGraphs pitching for {season}...[/blue]')
    result = download_fangraphs_pitching(season=season, output_dir=output_dir)

    if result.success:
        console.print(
            f'[green]✓[/green] Downloaded {result.rows_downloaded} records '
            f'in {result.duration_seconds:.2f}s'
        )
    else:
        console.print(f'[red]✗[/red] {result.error}')
        raise typer.Exit(code=1)


# ESPN Command
@app.command()
def espn_scoreboard(
    date_str: Optional[str] = typer.Option(None, '--date', '-d', help='Date (YYYYMMDD)'),
    output_dir: Path = typer.Option(Path('data/raw/espn'), '--output', '-o'),
) -> None:
    """Download ESPN scoreboard."""
    console.print('[blue]Downloading ESPN scoreboard...[/blue]')
    result = download_espn_scoreboard(date_str=date_str, output_dir=output_dir)

    if result.success:
        console.print(
            f'[green]✓[/green] Downloaded {result.rows_downloaded} games '
            f'in {result.duration_seconds:.2f}s'
        )
    else:
        console.print(f'[red]✗[/red] {result.error}')
        raise typer.Exit(code=1)


# Weather Command
@app.command()
def weather_forecast(
    venue_name: str = typer.Option(..., '--venue', '-v', help='Venue name'),
    latitude: float = typer.Option(..., '--lat', help='Latitude'),
    longitude: float = typer.Option(..., '--lon', help='Longitude'),
    output_dir: Path = typer.Option(Path('data/raw/weather'), '--output', '-o'),
) -> None:
    """Download weather forecast for venue."""
    console.print(f'[blue]Downloading forecast for {venue_name}...[/blue]')
    result = download_weather_forecast(
        latitude=latitude,
        longitude=longitude,
        venue_name=venue_name,
        output_dir=output_dir,
    )

    if result.success:
        console.print(
            f'[green]✓[/green] Downloaded {result.rows_downloaded} forecast periods '
            f'in {result.duration_seconds:.2f}s'
        )
    else:
        console.print(f'[red]✗[/red] {result.error}')
        raise typer.Exit(code=1)