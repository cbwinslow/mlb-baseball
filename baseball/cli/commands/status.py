"""Status CLI Commands

Name:    status.py
Date:    2026-05-11
Version: 1.0.0

Description:
    Commands to report system health, data freshness, and pipeline coverage.
"""

import os
from datetime import datetime
from pathlib import Path

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


def _check_db_connection(db_url: str) -> tuple[bool, str]:
    """Attempt a live DB connection and return (ok, message)."""
    try:
        import psycopg2  # type: ignore

        conn = psycopg2.connect(db_url, connect_timeout=5)
        cur = conn.cursor()
        cur.execute("SELECT version();")
        version = cur.fetchone()[0]
        conn.close()
        return True, version.split(",")[0]
    except ImportError:
        return False, "psycopg2 not installed"
    except Exception as exc:
        return False, str(exc)


@app.command()
def system() -> None:
    """Show system health: DB connectivity, environment, dependencies.

    Examples:
        baseball status system
    """
    console.print("[bold cyan]System Status[/bold cyan]")

    # --- Environment variables ---
    env_table = Table(title="Environment", show_header=True)
    env_table.add_column("Variable", style="cyan")
    env_table.add_column("Value", style="white")
    env_table.add_column("Status", style="bold")

    env_vars = [
        "DATABASE_URL",
        "DATA_DIR",
        "LOG_LEVEL",
        "MLB_RATE_LIMIT",
    ]
    for var in env_vars:
        val = os.environ.get(var)
        if val:
            # Mask password in DATABASE_URL
            display = val
            if var == "DATABASE_URL" and "@" in val:
                parts = val.split("@")
                creds = parts[0].split("//")[-1]
                user = creds.split(":")[0]
                display = val.replace(creds, f"{user}:***")
            env_table.add_row(var, display, "[green]SET[/green]")
        else:
            env_table.add_row(var, "-", "[red]NOT SET[/red]")
    console.print(env_table)

    # --- DB connectivity ---
    db_url = os.environ.get("DATABASE_URL")
    db_table = Table(title="Database", show_header=True)
    db_table.add_column("Check", style="cyan")
    db_table.add_column("Result", style="white")

    if db_url:
        ok, msg = _check_db_connection(db_url)
        status_str = "[green]CONNECTED[/green]" if ok else "[red]FAILED[/red]"
        db_table.add_row("Connection", status_str)
        db_table.add_row("Details", msg)
    else:
        db_table.add_row("Connection", "[yellow]SKIPPED (DATABASE_URL not set)[/yellow]")
    console.print(db_table)

    # --- Data directories ---
    data_table = Table(title="Data Directories", show_header=True)
    data_table.add_column("Path", style="cyan")
    data_table.add_column("Exists", style="white")
    data_table.add_column("Files", style="white")

    data_dir = Path(os.environ.get("DATA_DIR", "data"))
    dirs_to_check = [
        data_dir / "raw" / "mlb",
        data_dir / "raw" / "retrosheet",
        data_dir / "raw" / "statcast",
    ]
    for d in dirs_to_check:
        exists = d.exists()
        count = len(list(d.iterdir())) if exists else 0
        data_table.add_row(
            str(d),
            "[green]YES[/green]" if exists else "[red]NO[/red]",
            str(count),
        )
    console.print(data_table)


@app.command()
def data(
    season: int = typer.Option(
        None, help="Specific season to check (default: current year)"
    ),
) -> None:
    """Show data coverage and row counts by source and season.

    Examples:
        baseball status data
        baseball status data --season 2024
    """
    target_season = season or datetime.now().year
    console.print(f"[bold cyan]Data Coverage: {target_season}[/bold cyan]")

    db_url = os.environ.get("DATABASE_URL")

    sources = [
        ("MLB StatsAPI", "mlb_schedule", "season"),
        ("Retrosheet Events", "retro_events", "season"),
        ("Retrosheet GameLogs", "retro_gamelogs", "season"),
        ("StatCast", "statcast_pitches", "season"),
        ("Lahman", "lahman_batting", "year_id"),
    ]

    table = Table(title=f"Row Counts for {target_season}", show_header=True)
    table.add_column("Source", style="cyan")
    table.add_column("Table", style="white")
    table.add_column("Row Count", style="bold")
    table.add_column("Status", style="bold")

    if not db_url:
        for name, tbl, _ in sources:
            table.add_row(name, tbl, "-", "[yellow]NO DB URL[/yellow]")
        console.print(table)
        console.print(
            "[yellow]Set DATABASE_URL to enable live row count checks.[/yellow]"
        )
        return

    try:
        import psycopg2  # type: ignore

        conn = psycopg2.connect(db_url, connect_timeout=5)
        cur = conn.cursor()

        for name, tbl, season_col in sources:
            try:
                cur.execute(
                    f"SELECT COUNT(*) FROM {tbl} WHERE {season_col} = %s",
                    (target_season,),
                )
                count = cur.fetchone()[0]
                status = "[green]OK[/green]" if count > 0 else "[yellow]EMPTY[/yellow]"
                table.add_row(name, tbl, str(count), status)
            except Exception:
                table.add_row(name, tbl, "-", "[red]TABLE NOT FOUND[/red]")

        conn.close()
    except ImportError:
        for name, tbl, _ in sources:
            table.add_row(name, tbl, "-", "[red]psycopg2 not installed[/red]")
    except Exception as exc:
        for name, tbl, _ in sources:
            table.add_row(name, tbl, "-", f"[red]DB ERROR[/red]")
        console.print(f"[red]DB connection failed:[/red] {exc}")

    console.print(table)
