"""Tests for baseball.db.migrations (MigrationManager)."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from baseball.db.migrations import MigrationManager
from baseball.db.models import Base


@pytest.fixture(scope="module")
def engine():
    """Create an in-memory SQLite engine for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(engine):
    """Create a database session for each test."""
    with Session(engine) as session:
        yield session
        session.rollback()


@pytest.fixture
def sql_dir(tmp_path):
    """Create a temp directory with mock SQL migration files."""
    # Create some dummy migration files
    (tmp_path / "001_initial.sql").write_text("SELECT 1;")
    (tmp_path / "002_add_index.sql").write_text("SELECT 2;")
    return tmp_path


class TestMigrationManager:
    def test_instantiation(self, db_session):
        """Test that MigrationManager can be instantiated."""
        mgr = MigrationManager(session=db_session)
        assert mgr is not None

    def test_default_sql_directory(self, db_session):
        """Test that the default sql directory is 'sql'."""
        mgr = MigrationManager(session=db_session)
        assert mgr.sql_directory == Path("sql")

    def test_custom_sql_directory(self, db_session, tmp_path):
        """Test that a custom sql directory can be provided."""
        mgr = MigrationManager(session=db_session, sql_directory=tmp_path)
        assert mgr.sql_directory == tmp_path

    def test_discover_migrations_empty_dir(self, db_session, tmp_path):
        """Test discovering migrations in an empty directory."""
        mgr = MigrationManager(session=db_session, sql_directory=tmp_path)
        migrations = mgr._discover_migrations()
        assert migrations == {}

    def test_discover_migrations_with_files(self, db_session, sql_dir):
        """Test discovering migrations with SQL files present."""
        mgr = MigrationManager(session=db_session, sql_directory=sql_dir)
        migrations = mgr._discover_migrations()
        assert len(migrations) == 2
        assert "001" in migrations
        assert "002" in migrations

    def test_get_migration_checksum(self, db_session, sql_dir):
        """Test generating a checksum for a migration file."""
        mgr = MigrationManager(session=db_session, sql_directory=sql_dir)
        file_path = sql_dir / "001_initial.sql"
        checksum = mgr._get_migration_checksum(file_path)
        assert isinstance(checksum, str)
        assert len(checksum) == 64  # SHA256 hex digest

    def test_migration_checksum_deterministic(self, db_session, sql_dir):
        """Test that migration checksums are deterministic."""
        mgr = MigrationManager(session=db_session, sql_directory=sql_dir)
        file_path = sql_dir / "001_initial.sql"
        c1 = mgr._get_migration_checksum(file_path)
        c2 = mgr._get_migration_checksum(file_path)
        assert c1 == c2

    def test_get_migration_status_returns_dict(self, db_session, tmp_path):
        """Test that get_migration_status returns a dict."""
        mgr = MigrationManager(session=db_session, sql_directory=tmp_path)
        status = mgr.get_migration_status()
        assert isinstance(status, dict)
