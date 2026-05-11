"""Tests for baseball download CLI commands."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from baseball.cli.commands.download import app
from baseball.core.enums import ResultStatus, SourceType

runner = CliRunner()


def _ok_result():
    r = MagicMock()
    r.status = ResultStatus.SUCCESS
    r.rows_downloaded = 5
    r.bytes_downloaded = 512
    r.start_time = "2026-05-11T00:00:00"
    r.end_time = "2026-05-11T00:00:01"
    r.files_downloaded = []
    r.error = None
    r.error_code = None
    return r


def _fail_result():
    r = _ok_result()
    r.status = ResultStatus.FAILURE
    r.error = "connection error"
    return r


class TestMLBDownloadCommand:
    def test_schedule_success(self):
        with patch("baseball.cli.commands.download.MLBDownloader") as M:
            M.return_value.download_schedule.return_value = _ok_result()
            result = runner.invoke(app, ["mlbstatsapi", "--season", "2024"])
        assert result.exit_code == 0
        M.return_value.download_schedule.assert_called_once_with(season=2024)

    def test_game_success(self):
        with patch("baseball.cli.commands.download.MLBDownloader") as M:
            M.return_value.download_game.return_value = _ok_result()
            result = runner.invoke(
                app, ["mlbstatsapi", "--season", "2024", "--game-pk", "123456"]
            )
        assert result.exit_code == 0
        M.return_value.download_game.assert_called_once_with(game_pk=123456)

    def test_failure_exits_1(self):
        with patch("baseball.cli.commands.download.MLBDownloader") as M:
            M.return_value.download_schedule.return_value = _fail_result()
            result = runner.invoke(app, ["mlbstatsapi", "--season", "2024"])
        assert result.exit_code == 1

    def test_exception_exits_1(self):
        with patch("baseball.cli.commands.download.MLBDownloader") as M:
            M.return_value.download_schedule.side_effect = RuntimeError("boom")
            result = runner.invoke(app, ["mlbstatsapi", "--season", "2024"])
        assert result.exit_code == 1


class TestRetroSheetDownloadCommand:
    def test_events_success(self):
        with patch("baseball.cli.commands.download.RetroEventFileDownloader") as M:
            M.return_value.download_event_files.return_value = _ok_result()
            result = runner.invoke(
                app, ["retrosheet", "--season", "2024", "--type", "events"]
            )
        assert result.exit_code == 0
        M.return_value.download_event_files.assert_called_once_with(season=2024)

    def test_all_calls_both_methods(self):
        with patch("baseball.cli.commands.download.RetroEventFileDownloader") as M:
            M.return_value.download_event_files.return_value = _ok_result()
            M.return_value.download_game_logs.return_value = _ok_result()
            result = runner.invoke(
                app, ["retrosheet", "--season", "2024", "--type", "all"]
            )
        assert result.exit_code == 0
        M.return_value.download_event_files.assert_called_once()
        assert M.return_value.download_game_logs.call_count == 2


class TestStatcastDownloadCommand:
    def test_season_success(self):
        with patch("baseball.cli.commands.download.StatcastDownloader") as M:
            M.return_value.download_season.return_value = _ok_result()
            result = runner.invoke(
                app, ["statcast", "--start-date", "2024-04-01", "--season", "2024"]
            )
        assert result.exit_code == 0
        M.return_value.download_season.assert_called_once_with(season=2024)

    def test_derives_season_from_date(self):
        with patch("baseball.cli.commands.download.StatcastDownloader") as M:
            M.return_value.download_season.return_value = _ok_result()
            result = runner.invoke(
                app, ["statcast", "--start-date", "2023-04-01"]
            )
        assert result.exit_code == 0
        M.return_value.download_season.assert_called_once_with(season=2023)
