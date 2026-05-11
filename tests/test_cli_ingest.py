"""Tests for the ingest CLI commands."""

from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from baseball.cli.commands.ingest import app

runner = CliRunner()


def _ok_result():
    """Return a simple success-like object."""

    class R:
        success = True
        message = "ok"
        records_processed = 10

    return R()


class TestMLBStatsAPIIngestCommand:
    def test_season_success(self):
        with patch("baseball.cli.commands.ingest.MLBIngestor") as M:
            M.return_value.ingest_season.return_value = _ok_result()
            result = runner.invoke(app, ["mlbstatsapi", "--season", "2024"])
            assert result.exit_code == 0
            M.return_value.ingest_season.assert_called_once_with(season=2024)


class TestRetrosheetIngestCommand:
    def test_season_success(self):
        with patch("baseball.cli.commands.ingest.RetroEventFileIngestor") as M:
            M.return_value.ingest_season.return_value = _ok_result()
            result = runner.invoke(
                app, ["retrosheet", "--season", "2024", "--ingest-type", "events"]
            )
            assert result.exit_code == 0


class TestStatcastIngestCommand:
    def test_start_date_success(self):
        with patch("baseball.cli.commands.ingest.StatcastIngestor") as M:
            M.return_value.ingest_range.return_value = _ok_result()
            result = runner.invoke(
                app,
                ["statcast", "--start-date", "2024-04-01", "--end-date", "2024-04-30"],
            )
            assert result.exit_code == 0

    def test_season_derives_date_range(self):
        with patch("baseball.cli.commands.ingest.StatcastIngestor") as M:
            M.return_value.ingest_range.return_value = _ok_result()
            result = runner.invoke(
                app, ["statcast", "--start-date", "2024-04-01", "--season", "2024"]
            )
            assert result.exit_code == 0
