"""
================================================================================
Baseball CLI Main App
Name: app.py
Date: 2026-05-11
Script: app.py
Version: 2.0.0
Log Summary: Typer CLI application with all command groups
Description: Main entry point for the baseball CLI with database, download, ingest, validate, status
Change Summary: Updated to include database command group and proper imports
Inputs: CLI arguments and flags
Outputs: Command execution results, formatted output
================================================================================
"""


import typer
from rich.console import Console

from baseball import __version__
from baseball.cli.commands import db, download, ingest, status, validate

app = typer.Typer(
    name="baseball",
    help="Baseball analytics platform CLI",
    no_args_is_help=True,
)
console = Console()


@app.callback()
def main(
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable verbose output",
    ),
) -> None:
    """Baseball analytics platform."""
    if verbose:
        console.print("[dim]Verbose mode enabled[/dim]")


@app.command()
def version() -> None:
    """Show version information."""
    console.print(f"[bold blue]baseball[/bold blue] v{__version__}")


# Register command groups
app.add_typer(db.app, name="db")
app.add_typer(download.app, name="download")
app.add_typer(ingest.app, name="ingest")
app.add_typer(validate.app, name="validate")
app.add_typer(status.app, name="status")


if __name__ == "__main__":
    app()
