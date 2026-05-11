"""
Tests for baseball.db.bootstrap.DatabaseBootstrap

Uses SQLite (via SQLAlchemy) so no external Postgres instance is needed.
All tests are pure-Python and run in CI without additional dependencies.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

from baseball.db.bootstrap import DatabaseBootstrap


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_sql(directory: Path, filename: str, content: str) -> Path:
    """Write a SQL file under *directory* and return its Path."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / filename
    path.write_text(textwrap.dedent(content), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Tests: _discover_sql_files
# ---------------------------------------------------------------------------

class TestDiscoverSqlFiles:
    """Unit-tests for the SQL file discovery logic."""

    def test_returns_empty_list_when_sql_dir_missing(self, tmp_path: Path) -> None:
        bs = DatabaseBootstrap(sql_dir=tmp_path / "nonexistent")
        assert bs._discover_sql_files() == []

    def test_returns_empty_list_when_no_sql_files(self, tmp_path: Path) -> None:
        (tmp_path / "10_extensions").mkdir()
        bs = DatabaseBootstrap(sql_dir=tmp_path)
        assert bs._discover_sql_files() == []

    def test_discovers_files_recursively(self, tmp_path: Path) -> None:
        _write_sql(tmp_path / "10_extensions", "01_uuid.sql", "SELECT 1;")
        _write_sql(tmp_path / "20_schemas", "01_baseball.sql", "SELECT 2;")
        _write_sql(tmp_path / "50_tables_core", "01_schedule.sql", "SELECT 3;")
        bs = DatabaseBootstrap(sql_dir=tmp_path)
        found = bs._discover_sql_files()
        assert len(found) == 3

    def test_files_returned_in_lexical_order(self, tmp_path: Path) -> None:
        _write_sql(tmp_path / "50_tables_core", "02_b.sql", "SELECT 1;")
        _write_sql(tmp_path / "10_extensions", "01_a.sql", "SELECT 2;")
        _write_sql(tmp_path / "20_schemas", "01_c.sql", "SELECT 3;")
        bs = DatabaseBootstrap(sql_dir=tmp_path)
        found = bs._discover_sql_files()
        relative = [f.relative_to(tmp_path).parts[0] for f in found]
        assert relative == ["10_extensions", "20_schemas", "50_tables_core"]


# ---------------------------------------------------------------------------
# Tests: bootstrap()
# ---------------------------------------------------------------------------

class TestBootstrap:
    """Integration-style tests that execute SQL against an in-memory SQLite DB."""

    @pytest.fixture()
    def engine(self):
        """Provide an in-memory SQLite engine."""
        return create_engine("sqlite:///:memory:")

    def test_returns_false_when_no_db_connection(self, tmp_path: Path) -> None:
        _write_sql(tmp_path, "01_dummy.sql", "CREATE TABLE t (id INTEGER);")
        bs = DatabaseBootstrap(db_connection=None, sql_dir=tmp_path)
        assert bs.bootstrap() is False

    def test_returns_false_when_no_sql_files(self, engine, tmp_path: Path) -> None:
        bs = DatabaseBootstrap(db_connection=engine, sql_dir=tmp_path)
        assert bs.bootstrap() is False

    def test_executes_sql_and_returns_true(self, engine, tmp_path: Path) -> None:
        _write_sql(
            tmp_path,
            "01_create.sql",
            "CREATE TABLE test_table (id INTEGER PRIMARY KEY, name TEXT);",
        )
        bs = DatabaseBootstrap(db_connection=engine, sql_dir=tmp_path)
        result = bs.bootstrap()
        assert result is True
        # Verify the table actually exists
        insp = inspect(engine)
        assert "test_table" in insp.get_table_names()

    def test_executes_multiple_files_in_order(self, engine, tmp_path: Path) -> None:
        # File 01 creates the table; file 02 inserts a row - ORDER MATTERS
        _write_sql(
            tmp_path / "10_ddl",
            "01_create.sql",
            "CREATE TABLE ordered_test (val INTEGER);",
        )
        _write_sql(
            tmp_path / "20_dml",
            "01_insert.sql",
            "INSERT INTO ordered_test VALUES (42);",
        )
        bs = DatabaseBootstrap(db_connection=engine, sql_dir=tmp_path)
        assert bs.bootstrap() is True
        with engine.connect() as conn:
            row = conn.execute(text("SELECT val FROM ordered_test")).fetchone()
        assert row[0] == 42

    def test_skips_empty_sql_files(self, engine, tmp_path: Path) -> None:
        _write_sql(tmp_path, "01_empty.sql", "   \n   ")  # whitespace only
        _write_sql(tmp_path, "02_real.sql", "CREATE TABLE skip_test (id INTEGER);")
        bs = DatabaseBootstrap(db_connection=engine, sql_dir=tmp_path)
        assert bs.bootstrap() is True

    def test_returns_false_on_sql_error(self, engine, tmp_path: Path) -> None:
        _write_sql(tmp_path, "01_bad.sql", "THIS IS NOT VALID SQL !!!;")
        bs = DatabaseBootstrap(db_connection=engine, sql_dir=tmp_path)
        assert bs.bootstrap() is False
