"""
================================================================================
Database CLI Commands
Name: db.py
Date: 2026-05-11
Script: db.py
Version: 1.0.0
Log Summary: CLI commands for database initialization and management
Description: Database setup, migration, validation, and health check commands
Change Summary: Initial implementation with full database lifecycle support
Inputs: Database URL, CLI arguments
Outputs: Database state, validation reports, health status
================================================================================
"""

import os
import sys

import typer
from rich.console import Console
from rich.table import Table

from baseball.core.logging import get_logger
from baseball.db.connection import DatabaseConnectionManager
from baseball.db.schema import SchemaManager

logger = get_logger(__name__)
console = Console()

app = typer.Typer(
    name="db",
    help="Database initialization and management commands",
    no_args_is_help=True,
)


@app.command()
def init(
    drop_existing: bool = typer.Option(
        False,
        "--drop-existing",
        help="Drop all existing tables (DESTRUCTIVE)",
    ),
    echo_sql: bool = typer.Option(
        False,
        "--echo-sql",
        help="Log all SQL statements",
    ),
) -> None:
    """Initialize database schema and create all tables.

    Example:
        baseball db init
        baseball db init --drop-existing
    """
    try:
        console.print("[bold cyan]Initializing database...[/bold cyan]")

        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            console.print(
                "[red]Error: DATABASE_URL environment variable not set[/red]"
            )
            raise typer.Exit(code=1)

        # Create connection manager
        manager = DatabaseConnectionManager(
            database_url=database_url,
            echo_sql=echo_sql,
        )
        manager.initialize()

        # Create schema manager
        schema_manager = SchemaManager(manager.engine)

        # Test connection
        if not manager.health_check():
            console.print("[red]Failed to connect to database[/red]")
            raise typer.Exit(code=1)

        console.print("[green]✓[/green] Database connection successful")

        # Create tables
        if schema_manager.create_all_tables(drop_existing=drop_existing):
            console.print("[green]✓[/green] All tables created successfully")
        else:
            console.print("[red]Failed to create tables[/red]")
            raise typer.Exit(code=1)

        # Validate schema
        validation = schema_manager.validate_schema()
        console.print(
            f"\n[bold]Schema Validation:[/bold]"
            f"\n  Tables Expected: {validation['tables_expected']}"
            f"\n  Tables Found: {validation['tables_found']}"
        )

        if validation["validation_passed"]:
            console.print("[green]✓[/green] Schema validation passed")
        else:
            console.print("[yellow]⚠[/yellow] Schema validation issues:")
            if validation["missing_tables"]:
                console.print(
                    f"  Missing: {', '.join(validation['missing_tables'])}"
                )

        console.print("\n[bold green]Database initialization complete![/bold green]")
        manager.shutdown()

    except Exception as e:
        logger.exception(f"Database initialization failed: {e}")
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(code=1)


@app.command()
def status() -> None:
    """Show database status and schema information.

    Example:
        baseball db status
    """
    try:
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            console.print(
                "[red]Error: DATABASE_URL environment variable not set[/red]"
            )
            raise typer.Exit(code=1)

        manager = DatabaseConnectionManager(database_url=database_url)
        manager.initialize()

        # Health check
        console.print("[bold cyan]Database Status[/bold cyan]")
        if manager.health_check():
            console.print("[green]✓ Connection: OK[/green]")
        else:
            console.print("[red]✗ Connection: FAILED[/red]")
            raise typer.Exit(code=1)

        # Pool status
        pool_status = manager.get_pool_status()
        if pool_status:
            console.print(
                f"[cyan]Connection Pool:[/cyan]"
                f"\n  Size: {pool_status['pool_size']}"
                f"\n  Checked Out: {pool_status['checked_out']}"
                f"\n  Total Available: {pool_status['total_connections']}"
            )

        # Schema status
        schema_manager = SchemaManager(manager.engine)
        validation = schema_manager.validate_schema()
        console.print(
            f"\n[cyan]Schema:[/cyan]"
            f"\n  Tables Found: {validation['tables_found']}"
            f"\n  Tables Expected: {validation['tables_expected']}"
        )

        if validation["validation_passed"]:
            console.print("  Status: [green]✓ Valid[/green]")
        else:
            console.print("  Status: [red]✗ Invalid[/red]")

        # Row counts
        console.print("\n[cyan]Table Sizes:[/cyan]")
        counts = schema_manager.get_row_counts()

        table = Table(title="Table Row Counts", show_header=True)
        table.add_column("Table", style="cyan")
        table.add_column("Rows", style="magenta", justify="right")

        for table_name in sorted(counts.keys()):
            count = counts[table_name]
            if count is not None:
                table.add_row(table_name, str(count))
            else:
                table.add_row(table_name, "[red]N/A[/red]")

        console.print(table)
        manager.shutdown()

    except Exception as e:
        logger.exception(f"Failed to get database status: {e}")
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(code=1)


@app.command()
def validate() -> None:
    """Validate database schema and constraints.

    Example:
        baseball db validate
    """
    try:
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            console.print(
                "[red]Error: DATABASE_URL environment variable not set[/red]"
            )
            raise typer.Exit(code=1)

        manager = DatabaseConnectionManager(database_url=database_url)
        manager.initialize()

        if not manager.health_check():
            console.print("[red]Failed to connect to database[/red]")
            raise typer.Exit(code=1)

        console.print("[bold cyan]Validating Schema[/bold cyan]\n")

        schema_manager = SchemaManager(manager.engine)
        validation = schema_manager.validate_schema()

        # Display results
        console.print(f"Tables Expected: {validation['tables_expected']}")
        console.print(f"Tables Found: {validation['tables_found']}")

        if validation["missing_tables"]:
            console.print(
                f"\n[yellow]Missing Tables ({len(validation['missing_tables'])}):[/yellow]"
            )
            for table_name in validation["missing_tables"]:
                console.print(f"  - {table_name}")

        if validation["extra_tables"]:
            console.print(
                f"\n[yellow]Extra Tables ({len(validation['extra_tables'])}):[/yellow]"
            )
            for table_name in validation["extra_tables"]:
                console.print(f"  - {table_name}")

        if validation["validation_passed"]:
            console.print("\n[green]✓ Schema validation passed[/green]")
        else:
            console.print("\n[red]✗ Schema validation failed[/red]")
            raise typer.Exit(code=1)

        manager.shutdown()

    except Exception as e:
        logger.exception(f"Schema validation failed: {e}")
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(code=1)
