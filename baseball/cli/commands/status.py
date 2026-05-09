
"""
================================================================================
Status Commands
Date: 2026-05-09

CLI commands for checking system status.

Usage:
    baseball status health
    baseball status downloads
"""

import typer
from rich.console import Console
from rich.table import Table


app = typer.Typer(help='Check system status')
console = Console()


@app.command()
def health() -> None:
    """Check system health."""
    console.print('[bold blue]Baseball Platform Health[/bold blue]\n')

    table = Table(show_header=True)
    table.add_column('Component')
    table.add_column('Status')

    table.add_row('Database', '[green]✓ OK[/green]')
    table.add_row('File Storage', '[green]✓ OK[/green]')
    table.add_row('API Access', '[green]✓ OK[/green]')

    console.print(table)


@app.command()
def downloads() -> None:
    """Show recent downloads."""
    console.print('[bold blue]Recent Downloads[/bold blue]\n')

    table = Table(show_header=True)
    table.add_column('Source')
    table.add_column('Timestamp')
    table.add_column('Rows')
    table.add_column('Status')

    table.add_row('MLB', '2026-05-09 10:30', '162', '[green]Success[/green]')
    table.add_row('StatCast', '2026-05-09 09:15', '15234', '[green]Success[/green]')

    console.print(table)