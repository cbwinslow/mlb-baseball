"""
================================================================================
ESPN Downloader
Date: 2026-05-09

Download baseball data from ESPN API.
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


class ESPNDownloader:
    """Download data from ESPN API."""

    BASE_URL = "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb"

    def __init__(self, output_dir: Path = Path("data/raw/espn")):
        """Initialize downloader.

        Args:
            output_dir: Output directory
        """
        self.output_dir = Path(output_dir)
        self.client = httpx.Client(timeout=30.0)

    def download_scoreboard(
        self,
        date_str: str | None = None,
    ) -> DownloadResult:
        """Download scoreboard for date.

        Args:
            date_str: Date string (YYYYMMDD format), defaults to today

        Returns:
            DownloadResult
        """
        result = DownloadResult(
            source=SourceType.ESPN,
            status=ResultStatus.FAILED,
        )
        result.start_time = datetime.now()

        try:
            if date_str is None:
                date_str = datetime.now().strftime("%Y%m%d")

            logger.info(f"Downloading ESPN scoreboard for {date_str}")

            url = f"{self.BASE_URL}/scoreboard"
            params = {"dates": date_str}

            response = self.client.get(url, params=params)
            response.raise_for_status()

            data = response.json()

            output_file = self.output_dir / f"scoreboard_{date_str}.json"
            save_json(data, output_file)

            games = data.get("events", [])

            result.status = ResultStatus.SUCCESS
            result.rows_downloaded = len(games)
            result.files_downloaded = [output_file]
            result.bytes_downloaded = output_file.stat().st_size

            logger.info(f"Downloaded {len(games)} games")

        except Exception as e:
            result.error = str(e)
            result.error_code = "DOWNLOAD_ERROR"
            logger.exception(f"Download failed: {e}")

        finally:
            result.end_time = datetime.now()

        return result
