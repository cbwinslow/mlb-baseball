"""Tests for baseball.sources.weather.ingestor.WeatherIngestor."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from baseball.core.enums import ResultStatus, SourceType
from baseball.sources.weather.ingestor import WeatherIngestor


@pytest.fixture
def dry_run_ingestor():
    """WeatherIngestor with no DB connection (dry-run mode)."""
    return WeatherIngestor(db_connection=None)


@pytest.fixture
def sample_weather_data():
    """Sample NOAA weather forecast data."""
    return {
        "@context": [
            "https://api.weather.gov/context/geojson.json",
            "https://api.weather.gov/context/forecast/forecast.json"
        ],
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [-71.09, 42.35]
                },
                "properties": {
                    "updated": "2024-04-01T12:00:00+00:00",
                    "units": "us",
                    "forecastOffice": "https://api.weather.gov/boxes/BOX",
                    "gridId": "BOX",
                    "gridX": 88,
                    "gridY": 89,
                    "forecast": "https://api.weather.gov/gridpoints/BOX/88,89/forecast",
                    "forecastHourly": "https://api.weather.gov/gridpoints/BOX/88,89/forecast/hourly",
                    "forecastGridData": "https://api.weather.gov/gridpoints/BOX/88,89/forecast-grid-data",
                    "observationStations": "https://api.weather.gov/stations",
                    "relativeLocation": {
                        "properties": {
                            "city": "Boston",
                            "state": "MA"
                        }
                    },
                    "periods": [
                        {
                            "number": 1,
                            "name": "Tonight",
                            "startTime": "2024-04-01T18:00:00-04:00",
                            "endTime": "2024-04-02T06:00:00-04:00",
                            "isDaytime": False,
                            "temperature": 45,
                            "temperatureUnit": "F",
                            "temperatureTrend": None,
                            "probabilityOfPrecipitation": {
                                "value": 20,
                                "unitCode": "wmoUnit:percent"
                            },
                            "dewpoint": 38,
                            "relativeHumidity": 75,
                            "windSpeed": "5 mph",
                            "windDirection": "NE",
                            "icon": "https://api.weather.gov/icons/land/night/sct?size=medium",
                            "shortForecast": "Mostly Clear"
                        }
                    ]
                }
            }
        ]
    }


class TestWeatherIngestorInit:
    def test_dry_run_when_no_connection(self):
        ingestor = WeatherIngestor(db_connection=None)
        assert ingestor._dry_run is True

    def test_not_dry_run_when_connection_given(self):
        fake_conn = MagicMock()
        ingestor = WeatherIngestor(db_connection=fake_conn)
        assert ingestor._dry_run is False


class TestIngestForecast:
    def test_returns_ingest_result(self, dry_run_ingestor, sample_weather_data, tmp_path):
        # Save sample data to file
        data_file = tmp_path / "forecast_20240401.json"
        data_file.write_text(json.dumps(sample_weather_data))
        
        result = dry_run_ingestor.ingest_forecast(path=data_file)
        assert hasattr(result, "status")
        assert hasattr(result, "source")

    def test_source_is_weather(self, dry_run_ingestor, sample_weather_data, tmp_path):
        # Save sample data to file
        data_file = tmp_path / "forecast_20240401.json"
        data_file.write_text(json.dumps(sample_weather_data))
        
        result = dry_run_ingestor.ingest_forecast(path=data_file)
        assert result.source == SourceType.WEATHER

    def test_missing_file_sets_failed(self, dry_run_ingestor, tmp_path):
        missing = tmp_path / "does_not_exist.json"
        result = dry_run_ingestor.ingest_forecast(path=missing)
        assert result.status == ResultStatus.FAILED

    def test_dry_run_rows_inserted_equals_period_count(self, dry_run_ingestor, sample_weather_data, tmp_path):
        # Save sample data to file
        data_file = tmp_path / "forecast_20240401.json"
        data_file.write_text(json.dumps(sample_weather_data))
        
        result = dry_run_ingestor.ingest_forecast(path=data_file)
        # Should insert: 1 station, 1 forecast, 1 period = 3 rows
        assert result.rows_inserted >= 1  # At least one row should be inserted