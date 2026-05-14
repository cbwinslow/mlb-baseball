"""
================================================================================
Weather Ingestor
Date: 2026-05-13
Script: ingestor.py
Version: 1.0.0

Load Weather downloaded JSON files into the database.
Supports dry-run mode when no DB connection is provided.

Inputs:  JSON files produced by WeatherDownloader
Outputs: Rows upserted into raw.weather_* tables
================================================================================
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.engine import Engine

from baseball.core.enums import ResultStatus, SourceType
from baseball.core.logging import get_logger
from baseball.core.results import IngestResult

logger = get_logger(__name__)


class WeatherIngestor:
    """Ingest Weather data into the database."""

    def __init__(self, db_connection: Optional[Engine] = None) -> None:
        """Initialize ingestor.

        Args:
            db_connection: SQLAlchemy Engine. When None the ingestor operates
                in dry-run / file-validation mode and will not write to DB.
        """
        self.db_connection = db_connection
        self._dry_run = db_connection is None
        if self._dry_run:
            logger.warning(
                "WeatherIngestor initialised without a DB connection – "
                "running in dry-run mode (no data will be written)"
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def ingest_forecast(
        self,
        path: Path,
    ) -> IngestResult:
        """Ingest a forecast JSON file produced by WeatherDownloader.

        Args:
            path: Path to the forecast JSON file.

        Returns:
            IngestResult with row counts and timing.
        """
        start = datetime.utcnow()
        stations_inserted = 0
        forecasts_inserted = 0
        periods_inserted = 0
        error = None

        try:
            if not path.exists():
                raise FileNotFoundError(f"Forecast file not found: {path}")

            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)

            if self._dry_run:
                logger.info(
                    "[dry-run] Would ingest weather forecast data from %s",
                    path,
                )
                # Count what would be inserted
                stations_inserted = 1  # One station per forecast
                forecasts_inserted = 1  # One forecast per file
                periods = data.get("properties", {}).get("periods", [])
                periods_inserted = len(periods)
            else:
                stations_inserted, forecasts_inserted, periods_inserted = self._ingest_forecast_data(data)

            status = ResultStatus.SUCCESS
            logger.info(
                "Weather forecast ingest complete: %d stations, %d forecasts, %d periods from %s",
                stations_inserted,
                forecasts_inserted,
                periods_inserted,
                path,
            )

        except Exception as exc:
            logger.exception("Weather forecast ingest failed: %s", exc)
            status = ResultStatus.FAILED
            error = str(exc)

        return IngestResult(
            source=SourceType.WEATHER,
            status=status,
            rows_inserted=stations_inserted + forecasts_inserted + periods_inserted,
            rows_skipped=0,
            start_time=start,
            end_time=datetime.utcnow(),
            error=error,
        )

    # ------------------------------------------------------------------
    # Private helpers – DB writes
    # ------------------------------------------------------------------

    def _ingest_forecast_data(self, data: dict) -> tuple[int, int, int]:
        """Ingest forecast data into raw tables.

        Args:
            data: Parsed Weather forecast JSON.

        Returns:
            Tuple of (stations_inserted, forecasts_inserted, periods_inserted).
        """
        stations_inserted = 0
        forecasts_inserted = 0
        periods_inserted = 0

        with self.db_connection.connect() as conn:
            # Extract station data from @id or properties
            station_id = self._extract_station_id(data)
            if station_id:
                # Ingest station
                station_params = self._map_station_row(data, station_id)
                conn.execute(text("""
                    INSERT INTO raw.weather_stations (
                        id, elevation, source_url, loaded_at
                    ) VALUES (
                        :id, :elevation, :source_url, now()
                    )
                    ON CONFLICT (id) DO UPDATE SET
                        elevation = EXCLUDED.elevation,
                        source_url = EXCLUDED.source_url,
                        loaded_at = now()
                """), station_params)
                stations_inserted = 1

            # Ingest forecast
            forecast_params = self._map_forecast_row(data, station_id)
            conn.execute(text("""
                INSERT INTO raw.weather_forecasts (
                    id, station_id, updated, units, forecast_generated_at, source_url, loaded_at
                ) VALUES (
                    :id, :station_id, :updated, :units, :forecast_generated_at, :source_url, now()
                )
                ON CONFLICT (id) DO UPDATE SET
                    station_id = EXCLUDED.station_id,
                    updated = EXCLUDED.updated,
                    units = EXCLUDED.units,
                    forecast_generated_at = EXCLUDED.forecast_generated_at,
                    source_url = EXCLUDED.source_url,
                    loaded_at = now()
            """), forecast_params)
            forecasts_inserted = 1

            # Ingest periods
            periods = data.get("properties", {}).get("periods", [])
            for period in periods:
                period_params = self._map_period_row(period, forecast_params["id"])
                conn.execute(text("""
                    INSERT INTO raw.weather_periods (
                        id, forecast_id, number, name, start_time, end_time, is_daytime,
                        temperature, temperature_unit, temperature_trend, wind_speed,
                        wind_direction, icon, short_forecast, detailed_forecast, source_url, loaded_at
                    ) VALUES (
                        :id, :forecast_id, :number, :name, :start_time, :end_time, :is_daytime,
                        :temperature, :temperature_unit, :temperature_trend, :wind_speed,
                        :wind_direction, :icon, :short_forecast, :detailed_forecast, :source_url, now()
                    )
                    ON CONFLICT (id) DO UPDATE SET
                        forecast_id = EXCLUDED.forecast_id,
                        number = EXCLUDED.number,
                        name = EXCLUDED.name,
                        start_time = EXCLUDED.start_time,
                        end_time = EXCLUDED.end_time,
                        is_daytime = EXCLUDED.is_daytime,
                        temperature = EXCLUDED.temperature,
                        temperature_unit = EXCLUDED.temperature_unit,
                        temperature_trend = EXCLUDED.temperature_trend,
                        wind_speed = EXCLUDED.wind_speed,
                        wind_direction = EXCLUDED.wind_direction,
                        icon = EXCLUDED.icon,
                        short_forecast = EXCLUDED.short_forecast,
                        detailed_forecast = EXCLUDED.detailed_forecast,
                        source_url = EXCLUDED.source_url,
                        loaded_at = now()
                """), period_params)
                periods_inserted += 1

            conn.commit()

        return stations_inserted, forecasts_inserted, periods_inserted

    # ------------------------------------------------------------------
    # Internal utilities – Mapping functions
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_station_id(data: dict) -> Optional[str]:
        """Extract station ID from weather data."""
        # Try to get station ID from properties or @id
        properties = data.get("properties", {})
        if "@id" in properties:
            # Extract ID from URL like https://api.weather.gov/stations/KABC
            station_url = properties["@id"]
            return station_url.split("/")[-1] if station_url else None
        return None

    @staticmethod
    def _map_station_row(data: dict, station_id: str) -> dict:
        """Map a weather station row to DB params."""
        def _str_or_none(val: Any) -> Optional[str]:
            return str(val).strip() if val not in (None, "", "null") else None

        properties = data.get("properties", {})
        return {
            "id": station_id,
            "elevation": _str_or_none(properties.get("elevation", {}).get("value")),
            "source_url": data.get("@id", ""),
        }

    @staticmethod
    def _map_forecast_row(data: dict, station_id: Optional[str]) -> dict:
        """Map a weather forecast row to DB params."""
        def _str_or_none(val: Any) -> Optional[str]:
            return str(val).strip() if val not in (None, "", "null") else None

        def _iso_to_timestamp(val: Any) -> Optional[str]:
            if val is None or val == "":
                return None
            # Keep as-is for now, assuming it's already in proper format
            return str(val).strip() if val not in (None, "", "null") else None

        properties = data.get("properties", {})
        return {
            "id": properties.get("@id", "").split("/")[-1] if properties.get("@id") else "unknown",
            "station_id": station_id,
            "updated": _iso_to_timestamp(properties.get("updated")),
            "units": _str_or_none(properties.get("units")),
            "forecast_generated_at": _iso_to_timestamp(properties.get("forecastGeneratedAt")),
            "source_url": data.get("@id", ""),
        }

    @staticmethod
    def _map_period_row(period: dict, forecast_id: str) -> dict:
        """Map a weather period row to DB params."""
        def _str_or_none(val: Any) -> Optional[str]:
            return str(val).strip() if val not in (None, "", "null") else None

        def _int_or_none(val: Any) -> Optional[int]:
            try:
                return int(val) if val not in (None, "", "null") else None
            except (ValueError, TypeError):
                return None

        def _iso_to_timestamp(val: Any) -> Optional[str]:
            if val is None or val == "":
                return None
            # Keep as-is for now, assuming it's already in proper format
            return str(val).strip() if val not in (None, "", "null") else None

        def _bool_or_none(val: Any) -> Optional[bool]:
            if val is None or val == "":
                return None
            if isinstance(val, bool):
                return val
            if isinstance(val, str):
                return val.lower() in ("true", "1", "yes", "on")
            return bool(val)

        return {
            "id": f"{forecast_id}_{period.get('number', 0)}",  # Create unique ID
            "forecast_id": forecast_id,
            "number": _int_or_none(period.get("number")),
            "name": _str_or_none(period.get("name")),
            "start_time": _iso_to_timestamp(period.get("startTime")),
            "end_time": _iso_to_timestamp(period.get("endTime")),
            "is_daytime": _bool_or_none(period.get("isDaytime")),
            "temperature": _int_or_none(period.get("temperature")),
            "temperature_unit": _str_or_none(period.get("temperatureUnit")),
            "temperature_trend": _str_or_none(period.get("temperatureTrend")),
            "wind_speed": _str_or_none(period.get("windSpeed")),
            "wind_direction": _str_or_none(period.get("windDirection")),
            "icon": _str_or_none(period.get("icon")),
            "short_forecast": _str_or_none(period.get("shortForecast")),
            "detailed_forecast": _str_or_none(period.get("detailedForecast")),
            "source_url": period.get("@id", ""),
        }