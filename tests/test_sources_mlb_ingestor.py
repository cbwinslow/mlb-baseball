"""Tests for baseball.sources.mlb.ingestor.MLBIngestor."""

import csv
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from baseball.core.enums import ResultStatus, SourceType
from baseball.sources.mlb.ingestor import MLBIngestor


@pytest.fixture
def dry_run_ingestor():
    """MLBIngestor with no DB connection (dry-run mode)."""
    return MLBIngestor(db_connection=None)


@pytest.fixture
def schedule_csv(tmp_path) -> Path:
    """Write a minimal schedule CSV and return the path."""
    p = tmp_path / "schedule_2024_all.csv"
    fieldnames = ["game_pk", "game_date", "season", "status",
                  "home_team", "away_team"]
    with p.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow({
            "game_pk": "748531",
            "game_date": "2024-04-01",
            "season": "2024",
            "status": "Final",
            "home_team": "NYY",
            "away_team": "BOS",
        })
    return p


class TestMLBIngestorInit:
    def test_dry_run_when_no_connection(self):
        ingestor = MLBIngestor(db_connection=None)
        assert ingestor._dry_run is True

    def test_not_dry_run_when_connection_given(self):
        fake_conn = MagicMock()
        ingestor = MLBIngestor(db_connection=fake_conn)
        assert ingestor._dry_run is False


class TestIngestSchedule:
    def test_returns_ingest_result(self, dry_run_ingestor, schedule_csv):
        result = dry_run_ingestor.ingest_schedule(path=schedule_csv, season=2024)
        assert hasattr(result, "status")
        assert hasattr(result, "source")

    def test_dry_run_rows_inserted_equals_row_count(self, dry_run_ingestor, schedule_csv):
        result = dry_run_ingestor.ingest_schedule(path=schedule_csv, season=2024)
        assert result.rows_inserted == 1

    def test_missing_file_sets_failed(self, dry_run_ingestor, tmp_path):
        missing = tmp_path / "does_not_exist.csv"
        result = dry_run_ingestor.ingest_schedule(path=missing, season=2024)
        assert result.status == ResultStatus.FAILED

    def test_source_is_mlb(self, dry_run_ingestor, schedule_csv):
        result = dry_run_ingestor.ingest_schedule(path=schedule_csv, season=2024)
        assert result.source == SourceType.MLB
