"""Tests for baseball.sources.retrosheet.ingestor.RetroEventFileIngestor."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from baseball.core.enums import ResultStatus, SourceType
from baseball.sources.retrosheet.ingestor import RetroEventFileIngestor


@pytest.fixture
def ingestor():
    return RetroEventFileIngestor(db_connection=None)


@pytest.fixture
def event_file(tmp_path) -> Path:
    """Create a minimal fake Retrosheet event file."""
    p = tmp_path / "2024NYA.EVA"
    p.write_text("id,NYA202404010\nversion,2\nstart,troutm001,\"Mike Trout\",1,4,8\n")
    return p


class TestRetroEventFileIngestorInit:
    def test_instantiates_with_no_db(self):
        ingestor = RetroEventFileIngestor(db_connection=None)
        assert ingestor is not None

    def test_instantiates_with_mock_db(self):
        ingestor = RetroEventFileIngestor(db_connection=MagicMock())
        assert ingestor is not None


class TestIngestEventFile:
    def test_returns_ingest_result(self, ingestor, event_file):
        with patch.object(ingestor.parser, "parse_file", return_value=[{"event": 1}]):
            result = ingestor.ingest_event_file(path=event_file, season=2024)
            assert hasattr(result, "status")
            assert hasattr(result, "source")

    def test_source_is_retrosheet(self, ingestor, event_file):
        with patch.object(ingestor.parser, "parse_file", return_value=[]):
            result = ingestor.ingest_event_file(path=event_file, season=2024)
            assert result.source == SourceType.RETROSHEET

    def test_parse_exception_sets_failed(self, ingestor, event_file):
        with patch.object(ingestor.parser, "parse_file",
                          side_effect=Exception("parse error")):
            result = ingestor.ingest_event_file(path=event_file, season=2024)
            assert result.status == ResultStatus.FAILED

    def test_rows_inserted_equals_events(self, ingestor, event_file):
        events = [{"event": i} for i in range(5)]
        with patch.object(ingestor.parser, "parse_file", return_value=events):
            result = ingestor.ingest_event_file(path=event_file, season=2024)
            assert result.rows_inserted == 5


class TestIngestGameLogs:
    def test_returns_ingest_result(self, ingestor, tmp_path):
        p = tmp_path / "GL2024.TXT"
        p.write_text("20240401,0,D,NYA,BOS\n")
        result = ingestor.ingest_game_logs(path=p, season=2024, league="AL")
        assert hasattr(result, "status")

    def test_missing_file_sets_failed(self, ingestor, tmp_path):
        missing = tmp_path / "MISSING.TXT"
        result = ingestor.ingest_game_logs(path=missing, season=2024, league="AL")
        assert result.status == ResultStatus.FAILED
