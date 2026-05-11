"""Tests for baseball.sources.statcast.downloader.StatcastDownloader."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from baseball.core.enums import ResultStatus, SourceType
from baseball.sources.statcast.downloader import StatcastDownloader


@pytest.fixture
def downloader(tmp_path):
    with patch("baseball.sources.statcast.downloader.statcast") as mock_sc:
        mock_sc.return_value = MagicMock()
        dl = StatcastDownloader(output_dir=tmp_path / "raw/statcast")
        yield dl


class TestStatcastDownloaderInit:
    def test_default_output_dir(self):
        dl = StatcastDownloader()
        assert "statcast" in str(dl.output_dir)

    def test_custom_output_dir(self, tmp_path):
        dl = StatcastDownloader(output_dir=tmp_path)
        assert dl.output_dir == tmp_path


class TestDownloadSeason:
    def test_returns_download_result(self, downloader):
        with patch("baseball.sources.statcast.downloader.statcast_batter",
                   return_value=MagicMock(shape=(100, 90))):
            result = downloader.download_season(season=2024)
            assert hasattr(result, "status")
            assert hasattr(result, "source")

    def test_source_is_statcast(self, downloader):
        with patch("baseball.sources.statcast.downloader.statcast_batter",
                   return_value=MagicMock(shape=(50, 90))):
            result = downloader.download_season(season=2024)
            assert result.source == SourceType.STATCAST

    def test_api_error_sets_failed(self, downloader):
        with patch("baseball.sources.statcast.downloader.statcast_batter",
                   side_effect=Exception("pybaseball error")):
            result = downloader.download_season(season=2024)
            assert result.status == ResultStatus.FAILED


class TestDownloadPitcher:
    def test_returns_download_result(self, downloader):
        with patch("baseball.sources.statcast.downloader.statcast_pitcher",
                   return_value=MagicMock(shape=(200, 90))):
            result = downloader.download_pitcher(pitcher_id=543037)
            assert hasattr(result, "status")

    def test_error_sets_failed(self, downloader):
        with patch("baseball.sources.statcast.downloader.statcast_pitcher",
                   side_effect=Exception("API error")):
            result = downloader.download_pitcher(pitcher_id=999999)
            assert result.status == ResultStatus.FAILED


class TestDownloadBatter:
    def test_returns_download_result(self, downloader):
        with patch("baseball.sources.statcast.downloader.statcast_batter",
                   return_value=MagicMock(shape=(150, 90))):
            result = downloader.download_batter(batter_id=545361)
            assert hasattr(result, "status")

    def test_error_sets_failed(self, downloader):
        with patch("baseball.sources.statcast.downloader.statcast_batter",
                   side_effect=Exception("player not found")):
            result = downloader.download_batter(batter_id=999999)
            assert result.status == ResultStatus.FAILED
