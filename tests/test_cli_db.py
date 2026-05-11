"""Tests for baseball.cli.commands.db (database CLI commands)."""

import os
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from baseball.cli.commands.db import app

runner = CliRunner()


class TestDbInit:
    def test_init_missing_database_url(self):
        """Test that init fails when DATABASE_URL is not set."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove DATABASE_URL if present
            env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
            with patch.dict(os.environ, env, clear=True):
                result = runner.invoke(app, ["init"])
                assert result.exit_code != 0

    def test_init_help(self):
        """Test that init help is displayed."""
        result = runner.invoke(app, ["init", "--help"])
        assert result.exit_code == 0
        assert "init" in result.output.lower() or "help" in result.output.lower()

    def test_init_with_mock_db(self):
        """Test init with a mocked database connection."""
        with patch.dict(os.environ, {"DATABASE_URL": "sqlite:///test.db"}):
            mock_manager = MagicMock()
            mock_manager.initialize.return_value = True
            mock_manager.health_check.return_value = True
            mock_schema = MagicMock()
            mock_schema.create_all_tables.return_value = True

            with patch("baseball.cli.commands.db.DatabaseConnectionManager", return_value=mock_manager):
                with patch("baseball.cli.commands.db.SchemaManager", return_value=mock_schema):
                    result = runner.invoke(app, ["init"])
                    assert result.exit_code == 0


class TestDbHelp:
    def test_app_help(self):
        """Test that the db app shows help."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0

    def test_app_lists_commands(self):
        """Test that help shows available commands."""
        result = runner.invoke(app, ["--help"])
        assert "init" in result.output
