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
from baseball.sources.fangraphs.ingestor import FanGraphsIngestor
from baseball.sources.lahman.ingestor import LahmanIngestor
from baseball.sources.espn.ingestor import ESPNIngestor
from baseball.sources.weather.ingestor import WeatherIngestor

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
            data_dir.glob("game_*.json")
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


@app.command()
def fangraphs(
    data_type: str = typer.Option(..., help="Type of data: batting, pitching, fielding"),
    season: int = typer.Option(..., help="Season to ingest"),
    data_dir: Path = typer.Option(
        Path("data/raw/fangraphs"),
        "--data-dir",
        help="Directory containing downloaded FanGraphs files",
    ),
    db_url: str = typer.Option(
        None,
        "--db-url",
        envvar="DATABASE_URL",
        help="Database connection URL (or set DATABASE_URL env var)",
    ),
) -> None:
    """Ingest FanGraphs data into the database.
    
    Examples:
        baseball ingest fangraphs --data-type batting --season 2024
        baseball ingest fangraphs --data-type pitching --season 2024
        baseball ingest fangraphs --data-type fielding --season 2024
    """
    try:
        ingestor = FangraphsIngestor(db_connection=db_url)
        
        # Map data type to file pattern
        file_patterns = {
            "batting": f"fg_batting_{season}*.csv",
            "pitching": f"fg_pitching_{season}*.csv", 
            "fielding": f"fg_fielding_{season}*.csv"
        }
        
        if data_type not in file_patterns:
            console.print(f"[red]Invalid data type: {data_type}. Must be one of: batting, pitching, fielding[/red]")
            raise typer.Exit(code=1)
            
        pattern = file_patterns[data_type]
        data_files = sorted(data_dir.glob(pattern)) or sorted(
            data_dir.glob(f"*{data_type}*{season}*.csv")
        )
        
        if not data_files:
            console.print(
                f"[yellow]No {data_type} CSV files found in {data_dir} for season {season}.\n"
                f"Run: baseball download fangraphs --data-type {data_type} --season {season}[/yellow]"
            )
            return
            
        for df in data_files:
            if data_type == "batting":
                result = ingestor.ingest_batting(path=df, season=season)
                _print_ingest_result(f"FanGraphs batting: {df.name}", result)
            elif data_type == "pitching":
                result = ingestor.ingest_pitching(path=df, season=season)
                _print_ingest_result(f"FanGraphs pitching: {df.name}", result)
            elif data_type == "fielding":
                result = ingestor.ingest_fielding(path=df, season=season)
                _print_ingest_result(f"FanGraphs fielding: {df.name}", result)

    except Exception as exc:
        logger.exception("FanGraphs ingest failed: %s", exc)
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc


@app.command()
def lahman(
    data_type: str = typer.Option(..., help="Type of data: people, batting, pitching, fielding, etc."),
    data_dir: Path = typer.Option(
        Path("data/raw/lahman"),
        "--data-dir",
        help="Directory containing extracted Lahman CSV files",
    ),
    db_url: str = typer.Option(
        None,
        "--db-url",
        envvar="DATABASE_URL",
        help="Database connection URL (or set DATABASE_URL env var)",
    ),
) -> None:
    """Ingest Lahman data into the database.
    
    Examples:
        baseball ingest lahman --data-type people
        baseball ingest lahman --data-type batting
        baseball ingest lahman --data-type pitching
        baseball ingest lahman --data-type fielding
    """
    try:
        ingestor = LahmanIngestor(db_connection=db_url)
        
        # Map data type to filename
        file_map = {
            "people": "People.csv",
            "batting": "Batting.csv",
            "pitching": "Pitching.csv",
            "fielding": "Fielding.csv",
            "managers": "Managers.csv",
            "awardsmanagers": "AwardsManagers.csv",
            "awardsplayers": "AwardsPlayers.csv",
            "allstarfull": "AllstarFull.csv",
            "appearances": "Appearances.csv",
            "collegeplaying": "CollegePlaying.csv",
            "halloffame": "HallOfFame.csv",
            "homegames": "HomeGames.csv",
            "pitchingpost": "PitchingPost.csv",
            "salaries": "Salaries.csv",
            "schools": "Schools.csv",
            "seriespost": "SeriesPost.csv",
            "teams": "Teams.csv",
            "teamsfranchises": "TeamsFranchises.csv",
            "teamshalf": "TeamsHalf.csv",
        }
        
        if data_type not in file_map:
            console.print(f"[red]Invalid data type: {data_type}. Must be one of: {', '.join(file_map.keys())}[/red]")
            raise typer.Exit(code=1)
            
        filename = file_map[data_type]
        data_file = data_dir / filename
        
        if not data_file.exists():
            console.print(
                f"[yellow]Lahman {data_type} file not found: {data_file}\n"
                f"Please extract the Lahman ZIP file and place CSV files in {data_dir}[/yellow]"
            )
            return
            
        result = ingestor.ingest_table(data_type=data_type, path=data_file)
        _print_ingest_result(f"Lahman {data_type}: {data_file.name}", result)

    except Exception as exc:
        logger.exception("Lahman ingest failed: %s", exc)
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc


@app.command()
def espn(
    start_date: str = typer.Option(..., help="Start date YYYY-MM-DD"),
    end_date: str = typer.Option(None, help="End date YYYY-MM-DD"),
    data_dir: Path = typer.Option(
        Path("data/raw/espn"),
        "--data-dir",
        help="Directory containing downloaded ESPN JSON files",
    ),
    db_url: str = typer.Option(
        None,
        "--db-url",
        envvar="DATABASE_URL",
        help="Database connection URL (or set DATABASE_URL env var)",
    ),
) -> None:
    """Ingest ESPN scoreboard data into the database.
    
    Examples:
        baseball ingest espn --start-date 2024-04-01 --end-date 2024-10-01
        baseball ingest espn --start-date 2024-04-01
    """
    try:
        ingestor = ESPIngestor(db_connection=db_url)
        target_start = start_date
        target_end = end_date or start_date  # Default to single day if no end date
        
        # Parse dates to generate expected filename patterns
        from datetime import datetime
        start_dt = datetime.strptime(target_start, "%Y-%m-%d")
        end_dt = datetime.strptime(target_end, "%Y-%m-%d")
        
        # Generate list of dates to check
        dates_to_check = []
        current_dt = start_dt
        while current_dt <= end_dt:
            dates_to_check.append(current_dt.strftime("%Y%m%d"))
            # Increment by one day
            from datetime import timedelta
            current_dt += timedelta(days=1)
        
        files_found = False
        for date_str in dates_to_check:
            # Look for scoreboard files for this date
            json_files = sorted(data_dir.glob(f"espn_scoreboard_{date_str}*.json"))
            if not json_files:
                # Try alternative pattern
                json_files = sorted(data_dir.glob(f"*scoreboard*{date_str}*.json"))
                
            for jf in json_files:
                result = ingestor.ingest_scoreboard(path=jf, date=date_str)
                _print_ingest_result(f"ESPN scoreboard: {jf.name}", result)
                files_found = True
                
        if not files_found:
            console.print(
                f"[yellow]No ESPN scoreboard JSON files found in {data_dir} for dates {target_start} to {target_end}.\n"
                f"Run: baseball download espn --start-date {target_start} --end-date {target_end}[/yellow]"
            )
            return

    except Exception as exc:
        logger.exception("ESPN ingest failed: %s", exc)
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc


@app.command()
def weather(
    start_date: str = typer.Option(..., help="Start date YYYY-MM-DD"),
    end_date: str = typer.Option(None, help="End date YYYY-MM-DD"),
    data_dir: Path = typer.Option(
        Path("data/raw/weather"),
        "--data-dir",
        help="Directory containing downloaded weather JSON files",
    ),
    db_url: str = typer.Option(
        None,
        "--db-url",
        envvar="DATABASE_URL",
        help="Database connection URL (or set DATABASE_URL env var)",
    ),
) -> None:
    """Ingest weather data into the database.
    
    Examples:
        baseball ingest weather --start-date 2024-04-01 --end-date 2024-10-01
        baseball ingest weather --start-date 2024-04-01
    """
    try:
        ingestor = WeatherIngestor(db_connection=db_url)
        target_start = start_date
        target_end = end_date or start_date  # Default to single day if no end date
        
        # Parse dates to generate expected filename patterns
        from datetime import datetime
        start_dt = datetime.strptime(target_start, "%Y-%m-%d")
        end_dt = datetime.strptime(target_end, "%Y-%m-%d")
        
        # Generate list of dates to check
        dates_to_check = []
        current_dt = start_dt
        while current_dt <= end_dt:
            dates_to_check.append(current_dt.strftime("%Y%m%d"))
            # Increment by one day
            from datetime import timedelta
            current_dt += timedelta(days=1)
        
        files_found = False
        for date_str in dates_to_check:
            # Look for weather files for this date
            json_files = sorted(data_dir.glob(f"weather_forecast_{date_str}*.json"))
            if not json_files:
                # Try alternative pattern
                json_files = sorted(data_dir.glob(f"*weather*{date_str}*.json"))
                
            for jf in json_files:
                result = ingestor.ingest_forecast(path=jf, date=date_str)
                _print_ingest_result(f"Weather forecast: {jf.name}", result)
                files_found = True
                
        if not files_found:
            console.print(
                f"[yellow]No weather JSON files found in {data_dir} for dates {target_start} to {target_end}.\n"
                f"Run: baseball download weather --start-date {target_start} --end-date {target_end}[/yellow]"
            )
            return

    except Exception as exc:
        logger.exception("Weather ingest failed: %s", exc)
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc
