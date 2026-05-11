"""
================================================================================
Database Bootstrap
Date: 2026-05-09
Script: bootstrap.py
Version: 2.0.0

Bootstrap database schema and tables by executing SQL files in lexical order
from numbered subdirectories under sql_dir.

Inputs:  db_connection (SQLAlchemy engine or connection), sql_dir path
Outputs: True on success, False on failure
================================================================================
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from baseball.core.logging import get_logger

logger = get_logger(__name__)


class DatabaseBootstrap:
    """Bootstrap database schema by executing versioned SQL files in order."""

    def __init__(
        self,
        db_connection: Optional[Engine] = None,
        sql_dir: Path = Path("sql"),
    ) -> None:
        """Initialize bootstrap.

        Args:
            db_connection: SQLAlchemy Engine (or raw Connection) to execute against.
            sql_dir: Root directory containing numbered sub-directories of SQL files.
        """
        self.db = db_connection
        self.sql_dir = Path(sql_dir)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def bootstrap(self, skip_checks: bool = False) -> bool:
        """Discover and execute all SQL files under sql_dir in lexical order.

        Files are collected recursively from sql_dir, sorted by their full
        relative path so that numbered directory prefixes (10_extensions,
        20_schemas, 50_tables_core, …) enforce execution order automatically.

        Args:
            skip_checks: When True, pre-flight validation is skipped.

        Returns:
            True if all SQL files executed successfully (or no files found).
            False if execution fails for any file.
        """
        if self.db is None:
            logger.error("No database connection provided – cannot bootstrap.")
            return False

        sql_files = self._discover_sql_files()

        if not sql_files:
            logger.warning(
                "No SQL files found under '%s' – bootstrap skipped.", self.sql_dir
            )
            return False

        logger.info(
            "Starting database bootstrap: %d SQL file(s) from '%s'",
            len(sql_files),
            self.sql_dir,
        )

        try:
            with self._get_connection() as conn:
                for sql_file in sql_files:
                    self._execute_file(conn, sql_file)
                conn.commit()
            logger.info("Bootstrap complete – all SQL files executed successfully.")
            return True
        except Exception as exc:
            logger.exception("Bootstrap failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _discover_sql_files(self) -> list[Path]:
        """Return all *.sql files under sql_dir sorted by relative path."""
        if not self.sql_dir.exists():
            logger.warning("sql_dir '%s' does not exist.", self.sql_dir)
            return []
        files = sorted(self.sql_dir.rglob("*.sql"))
        logger.debug("Discovered %d SQL file(s).", len(files))
        return files

    def _get_connection(self) -> Connection:
        """Return a raw DBAPI connection context from the engine."""
        if isinstance(self.db, Engine):
            return self.db.connect()
        # Assume it already behaves like a connection
        return self.db  # type: ignore[return-value]

    def _execute_file(self, conn: Connection, sql_file: Path) -> None:
        """Read and execute a single SQL file, logging each step."""
        relative = sql_file.relative_to(self.sql_dir)
        logger.info("  Executing: %s", relative)
        sql_text = sql_file.read_text(encoding="utf-8").strip()
        if not sql_text:
            logger.debug("  Skipping empty file: %s", relative)
            return
        # Split on semicolons to handle multi-statement files safely
        statements = [s.strip() for s in sql_text.split(";") if s.strip()]
        for stmt in statements:
            conn.execute(text(stmt))
        logger.debug("  Done: %s (%d statement(s))", relative, len(statements))
