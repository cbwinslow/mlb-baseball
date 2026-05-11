"""Tests for baseball.services.downloads orchestration functions."""

from unittest.mock import MagicMock, patch

import pytest

from baseball.core.enums import ResultStatus, SourceType
from baseball.services import downloads


class TestDownloadMLBSeason:
    def test_returns_download_result(self):
        with patch("baseball.services.downloads.MLBDownloader") as M:
            M.return_value.download_schedule.return_value = MagicMock(
                status=ResultStatus.SUCCESS,
                source=SourceType.MLB,
            )
            result = downloads.download_mlb_season(season=2024)
            assert result.status == ResultStatus.SUCCESS

    def test_error_sets_failed(self):
        with patch("baseball.services.downloads.MLBDownloader") as M:
            M.return_value.download_schedule.side_effect = Exception("API down")
            result = downloads.download_mlb_season(season=2024)
            assert result.status == ResultStatus.FAILED


class TestDownloadRetrosheet:
    def test_returns_result(self):
        with patch("baseball.services.downloads.RetroEventFileDownloader") as M:
            M.return_value.download_event_files.return_value = MagicMock(
                status=ResultStatus.SUCCESS,
                source=SourceType.RETROSHEET,
            )
            result = downloads.download_retrosheet_events(season=2024)
            assert result.status == ResultStatus.SUCCESS

    def test_error_sets_failed(self):
        with patch("baseball.services.downloads.RetroEventFileDownloader") as M:
            M.return_value.download_event_files.side_effect = Exception("404")
            result = downloads.download_retrosheet_events(season=2024)
            assert result.status == ResultStatus.FAILED


class TestDownloadStatcastSeason:
    def test_returns_result(self):
        with patch("baseball.services.downloads.StatcastDownloader") as M:
            M.return_value.download_season.return_value = MagicMock(
                status=ResultStatus.SUCCESS,
                source=SourceType.STATCAST,
            )
            result = downloads.download_statcast_season(season=2024)
            assert result.status == ResultStatus.SUCCESS

    def test_error_sets_failed(self):
        with patch("baseball.services.downloads.StatcastDownloader") as M:
            M.return_value.download_season.side_effect = Exception("timeout")
            result = downloads.download_statcast_season(season=2024)
            assert result.status == ResultStatus.FAILED
