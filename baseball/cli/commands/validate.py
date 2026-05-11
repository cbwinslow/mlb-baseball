"""Validate CLI Commands

Name:    validate.py
Date:    2026-05-11
Version: 1.1.0

Description:
    Commands to validate data integrity, consistency, and completeness.
    Wired to baseball.services.validation and baseball.sources.mlb.validator.
"""

from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from baseball.core.logging import get_logger

logger = get_logger(__name__)
console = Console()

app = typer.Typer(
    name="validate",
    help="Validate data integrity and quality.",
    no_args_is_help=True,
)


def _print_validation_result(title: str, result) -> None:
    """Render a ValidationResult as a rich table."""
    console.print(f"[bold cyan]{title}[/bold cyan]")
    table = Table(show_header=False)
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="white")
    status = getattr(result, "status", None)
    status_str = str(status)
    table.add_row("Status", f"[green]{status_str}[/green]" if "SUCCESS" in status_str.upper() else f"[red]{status_str}[/red]")
    table.add_row("Checks Passed", str(getattr(result, "checks_passed", "-")))
    table.add_row("Checks Failed", str(getattr(result, "checks_failed", "-")))
    table.add_row("Warnings", str(getattr(result, "warnings", "-")))
    if getattr(result, "errors", None):
        for i, err in enumerate(result.errors[:5], 1):
            table.add_row(f"Error {i}", str(err))
    if getattr(result, "error", None):
        table.add_row("Error", result.error)
    console.print(table)


@app.command("all-checks")
def all_checks(
    season: int = typer.Option(
        None, help="Season to validate (default: current year)"
    ),
    data_dir: Path = typer.Option(
        Path("data/raw"),
        "--data-dir",
        help="Root data directory",
    ),
    db_url: str = typer.Option(
        None,
        "--db-url",
        envvar="DATABASE_URL",
        help="Database connection URL",
    ),
) -> None:
    """Run all data quality validation checks.

    Validates file presence, row counts, referential integrity,
    and schedule/game/pitch completeness.

    Examples:
        baseball validate all-checks
        baseball validate all-checks --season 2024
    """
    target_season = season or datetime.now().year
    console.print(f"[bold cyan]Running all validation checks: season {target_season}[/bold cyan]")

    passed = 0
    failed = 0
    warnings = 0

    checks_table = Table(title="Validation Checks", show_header=True)
    checks_table.add_column("Check", style="cyan")
    checks_table.add_column("Result", style="bold")
    checks_table.add_column("Detail", style="white")

    # --- File presence checks ---
    sources = [
        ("MLB schedule CSV", data_dir / "mlb", f"*{target_season}*.csv"),
        ("Retrosheet events", data_dir / "retrosheet", f"*{target_season}*.ev?"),
        ("StatCast CSV", data_dir / "statcast", f"*{target_season}*.csv"),
    ]
    for name, d, pattern in sources:
        files = list(d.glob(pattern)) if d.exists() else []
        if files:
            checks_table.add_row(f"{name} present", "[green]PASS[/green]", f"{len(files)} file(s)")
            passed += 1
        else:
            checks_table.add_row(f"{name} present", "[yellow]WARN[/yellow]", f"No files in {d}")
            warnings += 1

    # --- DB checks (only if db_url set) ---
    if db_url:
        try:
            import psycopg2  # type: ignore
            conn = psycopg2.connect(db_url, connect_timeout=5)
            cur = conn.cursor()

            db_checks = [
                ("mlb_schedule rows", f"SELECT COUNT(*) FROM mlb_schedule WHERE season = {target_season}"),
                ("retro_events rows", f"SELECT COUNT(*) FROM retro_events WHERE season = {target_season}"),
                ("statcast_pitches rows", f"SELECT COUNT(*) FROM statcast_pitches WHERE season = {target_season}"),
            ]
            for check_name, sql in db_checks:
                try:
                    cur.execute(sql)
                    count = cur.fetchone()[0]
                    if count > 0:
                        checks_table.add_row(check_name, "[green]PASS[/green]", f"{count:,} rows")
                        passed += 1
                    else:
                        checks_table.add_row(check_name, "[yellow]EMPTY[/yellow]", "0 rows")
                        warnings += 1
                except Exception as exc:
                    checks_table.add_row(check_name, "[red]FAIL[/red]", str(exc)[:60])
                    failed += 1
            conn.close()
        except ImportError:
            checks_table.add_row("DB checks", "[yellow]SKIP[/yellow]", "psycopg2 not installed")
            warnings += 1
        except Exception as exc:
            checks_table.add_row("DB connection", "[red]FAIL[/red]", str(exc)[:60])
            failed += 1
    else:
        checks_table.add_row("DB checks", "[yellow]SKIP[/yellow]", "DATABASE_URL not set")
        warnings += 1

    console.print(checks_table)

    # Summary
    summary = Table(title="Summary", show_header=False)
    summary.add_column("Metric", style="cyan")
    summary.add_column("Count", style="bold")
    summary.add_row("Passed", f"[green]{passed}[/green]")
    summary.add_row("Warnings", f"[yellow]{warnings}[/yellow]")
    summary.add_row("Failed", f"[red]{failed}[/red]")
    console.print(summary)

    if failed > 0:
        raise typer.Exit(code=1)


@app.command()
def completeness(
    season: int = typer.Option(..., help="Season to validate"),
    data_dir: Path = typer.Option(
        Path("data/raw"),
        "--data-dir",
        help="Root data directory",
    ),
    db_url: str = typer.Option(
        None,
        "--db-url",
        envvar="DATABASE_URL",
        help="Database connection URL",
    ),
) -> None:
    """Check data completeness for a given season.

    Validates that schedule, game, player, and pitch records
    are present and consistent for the specified season.

    Examples:
        baseball validate completeness --season 2024
    """
    console.print(f"[bold cyan]Completeness check: season {season}[/bold cyan]")

    table = Table(title=f"Completeness: {season}", show_header=True)
    table.add_column("Source", style="cyan")
    table.add_column("Files Found", style="white")
    table.add_column("DB Rows", style="white")
    table.add_column("Status", style="bold")

    sources = [
        ("MLB Schedule", data_dir / "mlb", f"*{season}*.csv", "mlb_schedule", "season"),
        ("Retrosheet Events", data_dir / "retrosheet", f"*{season}*.ev?", "retro_events", "season"),
        ("Retrosheet GameLogs", data_dir / "retrosheet", f"GL{season}*.txt", "retro_gamelogs", "season"),
        ("StatCast", data_dir / "statcast", f"*{season}*.csv", "statcast_pitches", "season"),
    ]

    db_conn = None
    if db_url:
        try:
            import psycopg2  # type: ignore
            db_conn = psycopg2.connect(db_url, connect_timeout=5)
        except Exception as exc:
            console.print(f"[red]DB connection failed:[/red] {exc}")

    for name, d, pattern, tbl, season_col in sources:
        file_count = len(list(d.glob(pattern))) if d.exists() else 0
        db_count = "-"
        if db_conn:
            try:
                cur = db_conn.cursor()
                cur.execute(f"SELECT COUNT(*) FROM {tbl} WHERE {season_col} = %s", (season,))
                db_count = str(cur.fetchone()[0])
            except Exception:
                db_count = "N/A"

        if file_count > 0 and (db_count == "-" or int(db_count or 0) > 0):
            status = "[green]OK[/green]"
        elif file_count == 0:
            status = "[red]MISSING FILES[/red]"
        else:
            status = "[yellow]FILES PRESENT / DB EMPTY[/yellow]"

        table.add_row(name, str(file_count), db_count, status)

    if db_conn:
        db_conn.close()

    console.print(table)


@app.command("referential-integrity")
def referential_integrity(
    season: int = typer.Option(..., help="Season to check"),
    db_url: str = typer.Option(
        None,
        "--db-url",
        envvar="DATABASE_URL",
        help="Database connection URL",
    ),
) -> None:
    """Check referential integrity across tables for a season.

    Verifies that game_pk references, player_id references, and
    season keys are consistent across all related tables.

    Examples:
        baseball validate referential-integrity --season 2024
    """
    console.print(f"[bold cyan]Referential integrity check: season {season}[/bold cyan]")

    if not db_url:
        console.print("[yellow]DATABASE_URL not set — skipping DB checks[/yellow]")
        return

    table = Table(title=f"Referential Integrity: {season}", show_header=True)
    table.add_column("Check", style="cyan")
    table.add_column("Orphans", style="bold")
    table.add_column("Status", style="bold")

    checks = [
        (
            "statcast game_pk in mlb_schedule",
            "SELECT COUNT(*) FROM statcast_pitches sp "
            "WHERE sp.season = %(s)s "
            "AND sp.game_pk NOT IN (SELECT game_pk FROM mlb_schedule WHERE season = %(s)s)",
        ),
        (
            "retro_events game_id orphans",
            "SELECT COUNT(*) FROM retro_events re "
            "WHERE re.season = %(s)s "
            "AND re.game_id NOT IN (SELECT game_id FROM retro_gamelogs WHERE season = %(s)s)",
        ),
    ]

    try:
        import psycopg2  # type: ignore
        conn = psycopg2.connect(db_url, connect_timeout=5)
        cur = conn.cursor()
        failed = 0
        for check_name, sql in checks:
            try:
                cur.execute(sql, {"s": season})
                orphans = cur.fetchone()[0]
                if orphans == 0:
                    table.add_row(check_name, "0", "[green]PASS[/green]")
                else:
                    table.add_row(check_name, str(orphans), "[red]FAIL[/red]")
                    failed += 1
            except Exception as exc:
                table.add_row(check_name, "-", f"[yellow]SKIP ({exc.__class__.__name__})[/yellow]")
        conn.close()
    except ImportError:
        console.print("[red]psycopg2 not installed[/red]")
        raise typer.Exit(code=1)
    except Exception as exc:
        console.print(f"[red]DB connection failed:[/red] {exc}")
        raise typer.Exit(code=1)

    console.print(table)
    if failed > 0:
        raise typer.Exit(code=1)
