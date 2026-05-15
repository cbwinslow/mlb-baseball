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
        # Split SQL into statements, respecting dollar-quoted strings, strings, and comments
        statements = self._split_sql_into_statements(sql_text)
        for stmt in statements:
            if stmt.strip():  # Only execute non-empty statements
                conn.execute(text(stmt))
        logger.debug("  Done: %s (%d statement(s))", relative, len(statements))

    def _split_sql_into_statements(self, sql_text: str) -> list[str]:
        """Split SQL text into statements, respecting dollar-quoted strings, strings, and comments.
        
        This handles PostgreSQL-specific syntax like DO blocks that contain semicolons.
        """
        statements = []
        current_stmt = []
        i = 0
        in_dollar_quote = False
        dollar_quote_delimiter = None
        in_single_quote = False
        in_double_quote = False
        escape_next = False
        in_line_comment = False
        in_block_comment = False
        
        while i < len(sql_text):
            char = sql_text[i]
            
            if escape_next:
                escape_next = False
                current_stmt.append(char)
                i += 1
                continue
                
            if char == '\\' and (in_single_quote or in_double_quote) and not in_dollar_quote:
                escape_next = True
                current_stmt.append(char)
                i += 1
                continue
            
            # Handle dollar quotes (PostgreSQL specific)
            if not in_single_quote and not in_double_quote and not in_line_comment and not in_block_comment and not escape_next:
                if char == '$':
                    # Check if this is the start or end of a dollar quote
                    j = i + 1
                    # Extract the delimiter (if any)
                    delimiter_start = j
                    while j < len(sql_text) and sql_text[j] not in ('$', ';', ' ', '\n', '\t'):
                        j += 1
                    delimiter = sql_text[delimiter_start:j]
                    
                    if not in_dollar_quote:
                        # Starting a dollar quote
                        in_dollar_quote = True
                        dollar_quote_delimiter = delimiter
                        current_stmt.append(char)
                    else:
                        # Check if this is the ending delimiter
                        if sql_text[i:i+len(delimiter)+2] == f'${delimiter}$':
                            # Ending the dollar quote
                            in_dollar_quote = False
                            # Add the complete ending delimiter
                            current_stmt.append(sql_text[i:i+len(delimiter)+2])
                            i += len(delimiter) + 1  # Skip past the delimiter we just added
                        else:
                            current_stmt.append(char)
                elif char == "'" and not in_dollar_quote and not in_line_comment and not in_block_comment:
                    in_single_quote = not in_single_quote
                    current_stmt.append(char)
                elif char == '"' and not in_dollar_quote and not in_line_comment and not in_block_comment:
                    in_double_quote = not in_double_quote
                    current_stmt.append(char)
                elif char == '-':
                    # Check for comments
                    if i + 1 < len(sql_text):
                        if sql_text[i+1] == '-':
                            # Line comment
                            in_line_comment = True
                            current_stmt.append(char)
                            current_stmt.append(sql_text[i+1])
                            i += 2
                            continue
                        elif sql_text[i+1] == '*':
                            # Block comment
                            in_block_comment = True
                            current_stmt.append(char)
                            current_stmt.append(sql_text[i+1])
                            i += 2
                            continue
                elif char == ';' and not in_dollar_quote and not in_single_quote and not in_double_quote and not in_line_comment and not in_block_comment:
                    # End of statement
                    current_stmt.append(char)
                    stmt_text = ''.join(current_stmt).strip()
                    if stmt_text:
                        statements.append(stmt_text)
                    current_stmt = []
                else:
                    current_stmt.append(char)
            else:
                # Handle comment endings
                if in_line_comment and char == '\n':
                    in_line_comment = False
                    current_stmt.append(char)
                elif in_block_comment and i + 1 < len(sql_text):
                    if sql_text[i] == '*' and sql_text[i+1] == '/':
                        in_block_comment = False
                        current_stmt.append(char)
                        current_stmt.append(sql_text[i+1])
                        i += 2
                        continue
                    else:
                        current_stmt.append(char)
                else:
                    current_stmt.append(char)
            
            i += 1
        
        # Don't forget the last statement
        if current_stmt:
            stmt_text = ''.join(current_stmt).strip()
            if stmt_text:
                statements.append(stmt_text)
                
        return statements