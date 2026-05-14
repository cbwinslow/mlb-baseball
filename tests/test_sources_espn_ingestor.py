"""Tests for baseball.sources.espn.ingestor.ESPNIngestor."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from baseball.core.enums import ResultStatus, SourceType
from baseball.sources.espn.ingestor import ESPNIngestor


@pytest.fixture
def dry_run_ingestor():
    """ESPNIngestor with no DB connection (dry-run mode)."""
    return ESPNIngestor(db_connection=None)


@pytest.fixture
def sample_espn_data():
    """Sample ESPN scoreboard data."""
    return {
        "events": [
            {
                "id": "401472353",
                "date": "2024-04-01T00:00Z",
                "name": "New York Yankees at Boston Red Sox",
                "shortName": "Yankees at Red Sox",
                "competitions": [
                    {
                        "id": "401472353",
                        "date": "2024-04-01T00:00Z",
                        "attendance": 35214,
                        "venue": {
                            "id": "3833",
                            "fullName": "Fenway Park",
                            "address": {
                                "city": "Boston",
                                "state": "MA"
                            }
                        },
                        "competitors": [
                            {
                                "homeAway": "home",
                                "team": {
                                    "id": "3833",
                                    "displayName": "Boston Red Sox",
                                    "abbreviation": "BOS",
                                    "location": "Boston",
                                    "name": "Red Sox"
                                },
                                "score": "5",
                                "winner": True,
                                "records": [
                                    {
                                        "type": "overall",
                                        "summary": "8-5"
                                    }
                                ]
                            },
                            {
                                "homeAway": "away",
                                "team": {
                                    "id": "3833",
                                    "displayName": "New York Yankees",
                                    "abbreviation": "NYY",
                                    "location": "New York",
                                    "name": "Yankees"
                                },
                                "score": "3",
                                "winner": False,
                                "records": [
                                    {
                                        "type": "overall",
                                        "summary": "5-8"
                                    }
                                ]
                            }
                        ],
                        "broadcasts": [
                            {
                                "names": ["ESPN"],
                                "market": {
                                    "domain": "us",
                                    "country": "USA"
                                }
                            }
                        ]
                    }
                ]
            }
        ]
    }


class TestESPNIngestorInit:
    def test_dry_run_when_no_connection(self):
        ingestor = ESPNIngestor(db_connection=None)
        assert ingestor._dry_run is True

    def test_not_dry_run_when_connection_given(self):
        fake_conn = MagicMock()
        ingestor = ESPNIngestor(db_connection=fake_conn)
        assert ingestor._dry_run is False


class TestIngestScoreboard:
    def test_returns_ingest_result(self, dry_run_ingestor, sample_espn_data, tmp_path):
        # Save sample data to file
        data_file = tmp_path / "scoreboard_20240401.json"
        data_file.write_text(json.dumps(sample_espn_data))
        
        result = dry_run_ingestor.ingest_scoreboard(path=data_file)
        assert hasattr(result, "status")
        assert hasattr(result, "source")

    def test_source_is_espn(self, dry_run_ingestor, sample_espn_data, tmp_path):
        # Save sample data to file
        data_file = tmp_path / "scoreboard_20240401.json"
        data_file.write_text(json.dumps(sample_espn_data))
        
        result = dry_run_ingestor.ingest_scoreboard(path=data_file)
        assert result.source == SourceType.ESPN

    def test_missing_file_sets_failed(self, dry_run_ingestor, tmp_path):
        missing = tmp_path / "does_not_exist.json"
        result = dry_run_ingestor.ingest_scoreboard(path=missing)
        assert result.status == ResultStatus.FAILED

    def test_dry_run_rows_inserted_equals_event_count(self, dry_run_ingestor, sample_espn_data, tmp_path):
        # Save sample data to file
        data_file = tmp_path / "scoreboard_20240401.json"
        data_file.write_text(json.dumps(sample_espn_data))
        
        result = dry_run_ingestor.ingest_scoreboard(path=data_file)
        assert result.rows_inserted == 6  # 1 event + 1 competition + 2 teams + 1 venue + 1 broadcast + 0 odds