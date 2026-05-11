"""Tests for baseball.sources.mlb.downloader.MLBDownloader."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from baseball.core.enums import ResultStatus, SourceType
from baseball.sources.mlb.downloader import MLBDownloader


@pytest.fixture
def downloader(tmp_path):
    """MLBDownloader with temp output dir, no live client."""
    with patch("baseball.sources.mlb.downloader.MLBClient") as MockClient:
        MockClient.return_value = MagicMock()
        dl = MLBDownloader(output_dir=tmp_path / "raw/mlb")
        dl.client = MockClient.return_value
        yield dl


class TestMLBDownloaderInit:
    def test_default_output_dir(self):
        with patch("baseball.sources.mlb.downloader.MLBClient"):
            dl = MLBDownloader()
            assert str(dl.output_dir) == "data/raw/mlb"

    def test_custom_output_dir(self, tmp_path):
        with patch("baseball.sources.mlb.downloader.MLBClient"):
            dl = MLBDownloader(output_dir=tmp_path)
            assert dl.output_dir == tmp_path


class TestDownloadSchedule:
    def test_returns_download_result(self, downloader):
        downloader.client.get_schedule.return_value = {"dates": []}
        result = downloader.download_schedule(season=2024)
        assert hasattr(result, "status")
        assert hasattr(result, "source")

    def test_source_is_mlb(self, downloader):
        downloader.client.get_schedule.return_value = {"dates": []}
        result = downloader.download_schedule(season=2024)
        assert result.source == SourceType.MLB

    def test_api_error_sets_failed_status(self, downloader):
        downloader.client.get_schedule.side_effect = Exception("API error")
        result = downloader.download_schedule(season=2024)
        assert result.status == ResultStatus.FAILED
        assert result.error is not None

    def test_success_sets_success_status(self, downloader):
        downloader.client.get_schedule.return_value = {
            "dates": [{"games": [{"gamePk": 1, "gameDateTime": "2024-04-01T18:10:00Z",
                                  "season": "2024", "status": {"abstractGameCode": "F"},
                                  "teams": {"home": {"team": {"name": "NYY"}},
                                            "away": {"team": {"name": "BOS"}}}}]}]
        }
        result = downloader.download_schedule(season=2024)
        assert result.status == ResultStatus.SUCCESS


class TestDownloadGame:
    def test_returns_download_result(self, downloader):
        downloader.client.get_game.return_value = {"gamePk": 123}
        downloader.client.get_game_boxscore.return_value = {}
        downloader.client.get_game_playbyplay.return_value = {"allPlays": []}
        result = downloader.download_game(game_pk=123)
        assert hasattr(result, "status")

    def test_api_error_sets_failed(self, downloader):
        downloader.client.get_game.side_effect = Exception("network error")
        result = downloader.download_game(game_pk=999)
        assert result.status == ResultStatus.FAILED
