
"""
================================================================================
Validate Commands
Date: 2026-05-09

CLI commands for validating data.

Usage:
    baseball validate mlb-schedule --path data/raw/mlb/schedule_2025.csv
"""

import typer
from pathlib import Path
from rich.console import Console

from baseball.services.validation import validate_mlb_schedule


app = typer.Typer(help='Validate downloaded or ingested data')
console = Console()


@app.command()
def mlb_schedule(
    path: Path = typer.Option(..., '--path', '-p', help='Path to schedule CSV'),
) -> None:
    """Validate MLB schedule file."""
    console.print(f'[blue]Validating {path}...[/blue]')

    result = validate_mlb_schedule(path)

    console.print(
        f'Validated {result.records_validated} records: '
        f'{result.records_valid} valid, {result.records_invalid} invalid'
    )

    if result.issues:
        console.print('[yellow]Issues found:[/yellow]')
        for issue in result.issues:
            console.print(f'  - {issue}')

    if not result.success:
        raise typer.Exit(code=1)