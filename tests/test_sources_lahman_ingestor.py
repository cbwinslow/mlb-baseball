"""Tests for baseball.sources.lahman.ingestor.LahmanIngestor."""

import csv
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from baseball.core.enums import ResultStatus, SourceType
from baseball.sources.lahman.ingestor import LahmanIngestor


@pytest.fixture
def dry_run_ingestor():
    """LahmanIngestor with no DB connection (dry-run mode)."""
    return LahmanIngestor(db_connection=None)


@pytest.fixture
def people_csv(tmp_path) -> Path:
    """Write a minimal People.csv and return the path."""
    p = tmp_path / "People.csv"
    fieldnames = [
        "playerID", "birthYear", "birthMonth", "birthDay", "birthCountry",
        "birthState", "birthCity", "deathYear", "deathMonth", "deathDay",
        "deathCountry", "deathState", "deathCity", "nameFirst", "nameLast",
        "nameGiven", "weight", "height", "bats", "throws", "debut", "finalGame",
        "retroID", "bbrefID"
    ]
    with p.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow({
            "playerID": "test001",
            "birthYear": "1990",
            "birthMonth": "01",
            "birthDay": "01",
            "birthCountry": "USA",
            "birthState": "NY",
            "birthCity": "New York",
            "deathYear": "",
            "deathMonth": "",
            "deathDay": "",
            "deathCountry": "",
            "deathState": "",
            "deathCity": "",
            "nameFirst": "Test",
            "nameLast": "Player",
            "nameGiven": "Test Player",
            "weight": "180",
            "height": "72",
            "bats": "R",
            "throws": "R",
            "debut": "2024-04-01",
            "finalGame": "",
            "retroID": "test001",
            "bbrefID": "test001"
        })
    return p


@pytest.fixture
def batting_csv(tmp_path) -> Path:
    """Write a minimal Batting.csv and return the path."""
    p = tmp_path / "Batting.csv"
    fieldnames = [
        "playerID", "yearID", "stint", "teamID", "lgID", "G", "AB", "R", "H",
        "2B", "3B", "HR", "RBI", "SB", "CS", "BB", "SO", "IBB", "HBP", "SH",
        "SF", "GIDP"
    ]
    with p.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow({
            "playerID": "test001",
            "yearID": "2024",
            "stint": "1",
            "teamID": "NYY",
            "lgID": "AL",
            "G": "10",
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


class TestLahmanIngestorInit:
    def test_dry_run_when_no_connection(self):
        ingestor = LahmanIngestor(db_connection=None)
        assert ingestor._dry_run is True

    def test_not_dry_run_when_connection_given(self):
        fake_conn = MagicMock()
        ingestor = LahmanIngestor(db_connection=fake_conn)
        assert ingestor._dry_run is False


class TestIngestPeople:
    def test_returns_ingest_result(self, dry_run_ingestor, people_csv):
        result = dry_run_ingestor.ingest_people(path=people_csv)
        assert hasattr(result, "status")
        assert hasattr(result, "source")

    def test_source_is_lahman(self, dry_run_ingestor, people_csv):
        result = dry_run_ingestor.ingest_people(path=people_csv)
        assert result.source == SourceType.LAHMAN

    def test_missing_file_sets_failed(self, dry_run_ingestor, tmp_path):
        missing = tmp_path / "does_not_exist.csv"
        result = dry_run_ingestor.ingest_people(path=missing)
        assert result.status == ResultStatus.FAILED

    def test_dry_run_rows_inserted_equals_row_count(self, dry_run_ingestor, people_csv):
        result = dry_run_ingestor.ingest_people(path=people_csv)
        assert result.rows_inserted == 1


class TestIngestBatting:
    def test_returns_ingest_result(self, dry_run_ingestor, batting_csv):
        result = dry_run_ingestor.ingest_batting(path=batting_csv)
        assert hasattr(result, "status")
        assert hasattr(result, "source")

    def test_source_is_lahman(self, dry_run_ingestor, batting_csv):
        result = dry_run_ingestor.ingest_batting(path=batting_csv)
        assert result.source == SourceType.LAHMAN

    def test_missing_file_sets_failed(self, dry_run_ingestor, tmp_path):
        missing = tmp_path / "does_not_exist.csv"
        result = dry_run_ingestor.ingest_batting(path=missing)
        assert result.status == ResultStatus.FAILED

    def test_dry_run_rows_inserted_equals_row_count(self, dry_run_ingestor, batting_csv):
        result = dry_run_ingestor.ingest_batting(path=batting_csv)
        assert result.rows_inserted == 1