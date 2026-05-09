"""
================================================================================
Baseball CLI Main App
Date: 2026-05-09

Typer CLI application with all command groups.
================================================================================
"""

import sys

import typer
from rich.console import Console

from baseball import __version__
from baseball.cli.commands import download, ingest, validate, status


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
app.add_typer(download.app, name="download")
app.add_typer(ingest.app, name="ingest")
app.add_typer(validate.app, name="validate")
app.add_typer(status.app, name="status")


if __name__ == "__main__":
    app()
