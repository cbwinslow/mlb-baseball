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
def statcast_parquet(tmp_path) -> Path:
    """Create a minimal fake statcast parquet (as CSV for simplicity in tests)."""
    import pandas as pd
    p = tmp_path / "statcast_2024_04_01_2024_04_30.parquet"
    df = pd.DataFrame(
        {
            "pitch_type": ["FF", "SL"],
            "release_speed": [94.2, 82.3],
            "batter": [545361, 545361],
            "pitcher": [543037, 543037],
            "game_date": ["2024-04-01", "2024-04-01"],
            "game_pk": [748531, 748531],
        }
    )
    df.to_parquet(p, index=False)
    return p


class TestStatcastIngestorInit:
    def test_instantiates_with_no_db(self):
        ingestor = StatcastIngestor(db_connection=None)
        assert ingestor is not None

    def test_instantiates_with_mock_db(self):
        ingestor = StatcastIngestor(db_connection=MagicMock())
        assert ingestor is not None


class TestIngestRange:
    def test_returns_ingest_result(self, ingestor, statcast_parquet):
        result = ingestor.ingest_range(
            path=statcast_parquet,
            start_date="2024-04-01",
            end_date="2024-04-30",
        )
        assert hasattr(result, "status")
        assert hasattr(result, "source")

    def test_source_is_statcast(self, ingestor, statcast_parquet):
        result = ingestor.ingest_range(
            path=statcast_parquet,
            start_date="2024-04-01",
            end_date="2024-04-30",
        )
        assert result.source == SourceType.STATCAST

    def test_missing_file_sets_failed(self, ingestor, tmp_path):
        missing = tmp_path / "does_not_exist.parquet"
        result = ingestor.ingest_range(
            path=missing,
            start_date="2024-04-01",
            end_date="2024-04-30",
        )
        assert result.status == ResultStatus.FAILED

    def test_rows_inserted_equals_row_count(self, ingestor, statcast_parquet):
        result = ingestor.ingest_range(
            path=statcast_parquet,
            start_date="2024-04-01",
            end_date="2024-04-30",
        )
        assert result.rows_inserted == 2
