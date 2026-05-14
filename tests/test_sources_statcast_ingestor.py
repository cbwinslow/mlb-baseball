"""Tests for baseball.sources.statcast.ingestor.StatcastIngestor."""

import csv
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from baseball.core.enums import ResultStatus, SourceType
from baseball.sources.statcast.ingestor import StatcastIngestor


@pytest.fixture
def ingestor():
    return StatcastIngestor(db_connection=None)


@pytest.fixture
def statcast_csv(tmp_path) -> Path:
    """Create a minimal fake statcast CSV file."""
    p = tmp_path / "statcast_2024.csv"
    p.write_text("game_pk,game_date,release_speed,batter,pitcher,pitch_type\n748531,2024-04-01,94.2,545361,543037,FF\n748532,2024-04-02,82.3,545361,543037,SL\n")
    return p


class TestStatcastIngestorInit:
    def test_instantiates_with_no_db(self):
        ingestor = StatcastIngestor(db_connection=None)
        assert ingestor is not None

    def test_instantiates_with_mock_db(self):
        ingestor = StatcastIngestor(db_connection=MagicMock())
        assert ingestor is not None


class TestIngestSeason:
    def test_returns_ingest_result(self, ingestor, statcast_csv):
        result = ingestor.ingest_season(
            path=statcast_csv,
            season=2024,
        )
        assert hasattr(result, "status")
        assert hasattr(result, "source")

    def test_source_is_statcast(self, ingestor, statcast_csv):
        result = ingestor.ingest_season(
            path=statcast_csv,
            season=2024,
        )
        assert result.source == SourceType.STATCAST

    def test_missing_file_sets_failed(self, ingestor, tmp_path):
        missing = tmp_path / "does_not_exist.csv"
        result = ingestor.ingest_season(
            path=missing,
            season=2024,
        )
        assert result.status == ResultStatus.FAILED

    def test_rows_inserted_equals_row_count(self, ingestor, statcast_csv):
        result = ingestor.ingest_season(
            path=statcast_csv,
            season=2024,
        )
        assert result.rows_inserted == 2
