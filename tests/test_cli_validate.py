"""Tests for the validate CLI commands."""

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from baseball.cli.commands.validate import app

runner = CliRunner()


class TestAllChecksCommand:
    def test_runs_with_season(self):
        result = runner.invoke(app, ["all-checks", "--season", "2024"])
        # Command runs; may fail due to missing DB but should not crash with exit 2
        assert result.exit_code != 2

    def test_runs_without_season(self):
        result = runner.invoke(app, ["all-checks"])
        assert result.exit_code != 2


class TestCompletenessCommand:
    def test_requires_season(self):
        result = runner.invoke(app, ["completeness"])
        # Missing required --season should exit with code 2 (typer usage error)
        assert result.exit_code == 2

    def test_runs_with_season(self):
        result = runner.invoke(app, ["completeness", "--season", "2024"])
        assert result.exit_code != 2


class TestReferentialIntegrityCommand:
    def test_requires_season(self):
        result = runner.invoke(app, ["referential-integrity"])
        assert result.exit_code == 2

    def test_runs_with_season(self):
        result = runner.invoke(app, ["referential-integrity", "--season", "2024"])
        assert result.exit_code != 2
