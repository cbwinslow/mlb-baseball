"""
================================================================================
Weather Downloader
Date: 2026-05-09

Download weather data from NOAA.
================================================================================
"""

from datetime import datetime
from pathlib import Path

import httpx

from baseball.core.enums import ResultStatus, SourceType
from baseball.core.logging import get_logger
from baseball.core.results import DownloadResult
from baseball.sources.common.files import save_json

logger = get_logger(__name__)


class WeatherDownloader:
    """Download weather data from NOAA."""

    BASE_URL = "https://api.weather.gov"

    def __init__(self, output_dir: Path = Path("data/raw/weather")):
        """Initialize downloader.

        Args:
            output_dir: Output directory
        """
        self.output_dir = Path(output_dir)
        self.client = httpx.Client(
            timeout=30.0,
            headers={
                "User-Agent": "(MLB Weather Service, contact: info@example.com)",
            },
        )

    def download_forecast(
        self,
        latitude: float,
        longitude: float,
        venue_name: str,
    ) -> DownloadResult:
        """Download weather forecast for location.

        Args:
            latitude: Latitude
            longitude: Longitude
            venue_name: Venue name for file naming

        Returns:
            DownloadResult
        """
        result = DownloadResult(
            source=SourceType.WEATHER,
            status=ResultStatus.FAILED,
        )
        result.start_time = datetime.now()

        try:
            logger.info(f"Downloading weather forecast for {venue_name}")

            # Get grid point
            points_url = f"{self.BASE_URL}/points/{latitude},{longitude}"
            points_response = self.client.get(points_url)
            points_response.raise_for_status()
            points_data = points_response.json()

            # Get forecast URL
            forecast_url = points_data["properties"].get("forecast")
            if not forecast_url:
                result.error = "Could not get forecast URL"
                return result

            # Get forecast
            forecast_response = self.client.get(forecast_url)
            forecast_response.raise_for_status()
            forecast_data = forecast_response.json()

            # Save
            sanitized_name = venue_name.lower().replace(" ", "_")
            output_file = self.output_dir / f"forecast_{sanitized_name}.json"
            save_json(forecast_data, output_file)

            periods = forecast_data.get("properties", {}).get("periods", [])

            result.status = ResultStatus.SUCCESS
            result.rows_downloaded = len(periods)
            result.files_downloaded = [output_file]
            result.bytes_downloaded = output_file.stat().st_size

            logger.info(f"Downloaded {len(periods)} forecast periods")

        except Exception as e:
            result.error = str(e)
            result.error_code = "DOWNLOAD_ERROR"
            logger.exception(f"Download failed: {e}")

        finally:
            result.end_time = datetime.now()

        return result
