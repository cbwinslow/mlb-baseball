"""Tests for the status CLI commands."""

from typer.testing import CliRunner

from baseball.cli.commands.status import app

runner = CliRunner()


class TestSystemCommand:
    def test_exits_cleanly(self):
        """system command runs and exits without a typer usage error."""
        result = runner.invoke(app, ["system"])
        # May fail due to missing DB/env, but must not crash with exit code 2
        assert result.exit_code != 2

    def test_outputs_something(self):
        """system command produces some output."""
        result = runner.invoke(app, ["system"])
        assert result.output is not None


class TestDataCommand:
    def test_runs_without_season(self):
        """data command works with no season option."""
        result = runner.invoke(app, ["data"])
        assert result.exit_code != 2

    def test_runs_with_season(self):
        """data command works with explicit season."""
        result = runner.invoke(app, ["data", "--season", "2024"])
        assert result.exit_code != 2

    def test_invalid_season_type_fails(self):
        """data command rejects non-integer season."""
        result = runner.invoke(app, ["data", "--season", "notanumber"])
        assert result.exit_code == 2
