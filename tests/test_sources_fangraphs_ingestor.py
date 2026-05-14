"""Tests for baseball.sources.fangraphs.ingestor.FanGraphsIngestor."""

import csv
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from baseball.core.enums import ResultStatus, SourceType
from baseball.sources.fangraphs.ingestor import FanGraphsIngestor


@pytest.fixture
def dry_run_ingestor():
    """FanGraphsIngestor with no DB connection (dry-run mode)."""
    return FanGraphsIngestor(db_connection=None)


@pytest.fixture
def batting_csv(tmp_path) -> Path:
    """Write a minimal batting CSV and return the path."""
    p = tmp_path / "fg_batting_2024.csv"
    fieldnames = [
        "playerid", "Season", "Team", "Lg", "G", "PA", "AB", "R", "H", "2B", "3B", 
        "HR", "RBI", "SB", "CS", "BB", "SO", "IBB", "HBP", "SH", "SF", "GIDP"
    ]
    with p.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow({
            "playerid": "test001",
            "Season": "2024",
            "Team": "NYY",
            "Lg": "AL",
            "G": "10",
            "PA": "40",
            "AB": "35",
            "R": "5",
            "H": "8",
            "2B": "2",
            "3B": "0",
            "HR": "1",
            "RBI": "4",
            "SB": "1",
            "CS": "0",
            "BB": "3",
            "SO": "7",
            "IBB": "0",
            "HBP": "0",
            "SH": "0",
            "SF": "0",
            "GIDP": "1"
        })
    return p


@pytest.fixture
def pitching_csv(tmp_path) -> Path:
    """Write a minimal pitching CSV and return the path."""
    p = tmp_path / "fg_pitching_2024.csv"
    fieldnames = [
        "playerid", "Season", "Team", "Lg", "W", "L", "G", "GS", "CG", "SHO", 
        "SV", "IP", "H", "R", "ER", "HR", "BB", "IBB", "SO", "HBP", "BK", "WP", 
        "BF", "ERA", "FIP", "WHIP", "H9", "HR9", "BB9", "SO9"
    ]
    with p.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow({
            "playerid": "test001",
            "Season": "2024",
            "Team": "NYY",
            "Lg": "AL",
            "W": "5",
            "L": "3",
            "G": "15",
            "GS": "15",
            "CG": "0",
            "SHO": "0",
            "SV": "2",
            "IP": "90.0",
            "H": "75",
            "R": "30",
            "ER": "25",
            "HR": "5",
            "BB": "20",
            "IBB": "2",
            "SO": "85",
            "HBP": "3",
            "BK": "0",
            "WP": "4",
            "BF": "380",
            "ERA": "2.50",
            "FIP": "3.20",
            "WHIP": "1.06",
            "H9": "7.5",
            "HR9": "0.5",
            "BB9": "2.0",
            "SO9": "8.5"
        })
    return p


@pytest.fixture
def fielding_csv(tmp_path) -> Path:
    """Write a minimal fielding CSV and return the path."""
    p = tmp_path / "fg_fielding_2024.csv"
    fieldnames = [
        "playerid", "Season", "Team", "Lg", "Pos", "G", "GS", "Inn", "TC", "PO", 
        "A", "E", "DP", "FP"
    ]
    with p.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow({
            "playerid": "test001",
            "Season": "2024",
            "Team": "NYY",
            "Lg": "AL",
            "Pos": "SS",
            "G": "10",
            "GS": "10",
            "Inn": "90.0",
            "TC": "25",
            "PO": "8",
            "A": "15",
            "E": "2",
            "DP": "3",
            "FP": ".920"
        })
    return p


class TestFanGraphsIngestorInit:
    def test_dry_run_when_no_connection(self):
        ingestor = FanGraphsIngestor(db_connection=None)
        assert ingestor._dry_run is True

    def test_not_dry_run_when_connection_given(self):
        fake_conn = MagicMock()
        ingestor = FanGraphsIngestor(db_connection=fake_conn)
        assert ingestor._dry_run is False


class TestIngestBattingStats:
    def test_returns_ingest_result(self, dry_run_ingestor, batting_csv):
        result = dry_run_ingestor.ingest_batting_stats(path=batting_csv, season=2024)
        assert hasattr(result, "status")
        assert hasattr(result, "source")

    def test_source_is_fangraphs(self, dry_run_ingestor, batting_csv):
        result = dry_run_ingestor.ingest_batting_stats(path=batting_csv, season=2024)
        assert result.source == SourceType.FANGRAPHS

    def test_missing_file_sets_failed(self, dry_run_ingestor, tmp_path):
        missing = tmp_path / "does_not_exist.csv"
        result = dry_run_ingestor.ingest_batting_stats(path=missing, season=2024)
        assert result.status == ResultStatus.FAILED

    def test_dry_run_rows_inserted_equals_row_count(self, dry_run_ingestor, batting_csv):
        result = dry_run_ingestor.ingest_batting_stats(path=batting_csv, season=2024)
        assert result.rows_inserted == 1


class TestIngestPitchingStats:
    def test_returns_ingest_result(self, dry_run_ingestor, pitching_csv):
        result = dry_run_ingestor.ingest_pitching_stats(path=pitching_csv, season=2024)
        assert hasattr(result, "status")
        assert hasattr(result, "source")

    def test_source_is_fangraphs(self, dry_run_ingestor, pitching_csv):
        result = dry_run_ingestor.ingest_pitching_stats(path=pitching_csv, season=2024)
        assert result.source == SourceType.FANGRAPHS

    def test_missing_file_sets_failed(self, dry_run_ingestor, tmp_path):
        missing = tmp_path / "does_not_exist.csv"
        result = dry_run_ingestor.ingest_pitching_stats(path=missing, season=2024)
        assert result.status == ResultStatus.FAILED

    def test_dry_run_rows_inserted_equals_row_count(self, dry_run_ingestor, pitching_csv):
        result = dry_run_ingestor.ingest_pitching_stats(path=pitching_csv, season=2024)
        assert result.rows_inserted == 1


class TestIngestFieldingStats:
    def test_returns_ingest_result(self, dry_run_ingestor, fielding_csv):
        result = dry_run_ingestor.ingest_fielding_stats(path=fielding_csv, season=2024)
        assert hasattr(result, "status")
        assert hasattr(result, "source")

    def test_source_is_fangraphs(self, dry_run_ingestor, fielding_csv):
        result = dry_run_ingestor.ingest_fielding_stats(path=fielding_csv, season=2024)
        assert result.source == SourceType.FANGRAPHS

    def test_missing_file_sets_failed(self, dry_run_ingestor, tmp_path):
        missing = tmp_path / "does_not_exist.csv"
        result = dry_run_ingestor.ingest_fielding_stats(path=missing, season=2024)
        assert result.status == ResultStatus.FAILED

    def test_dry_run_rows_inserted_equals_row_count(self, dry_run_ingestor, fielding_csv):
        result = dry_run_ingestor.ingest_fielding_stats(path=fielding_csv, season=2024)
        assert result.rows_inserted == 1