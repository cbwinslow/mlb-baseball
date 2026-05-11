"""Tests for baseball.sources.retrosheet.downloader.RetroEventFileDownloader."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from baseball.core.enums import ResultStatus, SourceType
from baseball.sources.retrosheet.downloader import RetroEventFileDownloader


@pytest.fixture
def downloader(tmp_path):
    dl = RetroEventFileDownloader(output_dir=tmp_path / "raw/retrosheet")
    dl.client = MagicMock()
    return dl


class TestRetroEventFileDownloaderInit:
    def test_default_output_dir(self):
        dl = RetroEventFileDownloader()
        assert "retrosheet" in str(dl.output_dir)

    def test_custom_output_dir(self, tmp_path):
        dl = RetroEventFileDownloader(output_dir=tmp_path)
        assert dl.output_dir == tmp_path

    def test_team_codes_populated(self):
        dl = RetroEventFileDownloader()
        assert "NYY" in dl.TEAM_CODES
        assert "BOS" in dl.TEAM_CODES


class TestDownloadEventFiles:
    def test_returns_download_result(self, downloader):
        with patch.object(downloader, "_download_team_season",
                          return_value=(1, 1024)):
            result = downloader.download_event_files(season=2024)
            assert hasattr(result, "status")
            assert hasattr(result, "source")

    def test_source_is_retrosheet(self, downloader):
        with patch.object(downloader, "_download_team_season",
                          return_value=(1, 1024)):
            result = downloader.download_event_files(season=2024)
            assert result.source == SourceType.RETROSHEET

    def test_network_error_sets_failed(self, downloader):
        with patch.object(downloader, "_download_team_season",
                          side_effect=Exception("net error")):
            result = downloader.download_event_files(season=2024)
            assert result.status == ResultStatus.FAILED


class TestDownloadGameLogs:
    def test_returns_download_result(self, downloader):
        with patch.object(downloader, "_download_game_log_file",
                          return_value=(1, 2048)):
            result = downloader.download_game_logs(season=2024)
            assert hasattr(result, "status")

    def test_error_sets_failed(self, downloader):
        with patch.object(downloader, "_download_game_log_file",
                          side_effect=Exception("404")):
            result = downloader.download_game_logs(season=2024)
            assert result.status == ResultStatus.FAILED
