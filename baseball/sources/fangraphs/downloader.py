"""
================================================================================
FanGraphs Downloader
Date: 2026-05-09

Download FanGraphs statistics via CSV export URLs.
================================================================================
"""

from datetime import datetime
from io import StringIO
from pathlib import Path

import httpx
import pandas as pd

from baseball.core.enums import ResultStatus, SourceType
from baseball.core.logging import get_logger
from baseball.core.results import DownloadResult
from baseball.sources.common.files import save_csv

logger = get_logger(__name__)


class FanGraphsDownloader:
    """Download FanGraphs statistics."""

    BASE_URL = "https://www.fangraphs.com/leaders.aspx"

    def __init__(self, output_dir: Path = Path("data/raw/fangraphs")):
        """Initialize downloader.

        Args:
            output_dir: Output directory
        """
        self.output_dir = Path(output_dir)
        self.client = httpx.Client(
            timeout=30.0,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; BaseballBot)",
            },
        )

    def download_batting_stats(
        self,
        season: int,
        qual: int = 0,
    ) -> DownloadResult:
        """Download batting leaderboard.

        Args:
            season: Season year
            qual: Minimum plate appearances

        Returns:
            DownloadResult
        """
        result = DownloadResult(
            source=SourceType.FANGRAPHS,
            status=ResultStatus.FAILED,
        )
        result.start_time = datetime.now()

        try:
            logger.info(f"Downloading FanGraphs batting stats for {season}")

            params = {
                "pos": "all",
                "stats": "bat",
                "lg": "all",
                "qual": qual,
                "type": 8,
                "season": season,
                "season1": season,
                "ind": 0,
                "csv": 1,
            }

            response = self.client.get(self.BASE_URL, params=params)
            response.raise_for_status()

            df = pd.read_csv(StringIO(response.text))

            output_file = self.output_dir / f"batting_stats_{season}.csv"
            save_csv(df, output_file)

            result.status = ResultStatus.SUCCESS
            result.rows_downloaded = len(df)
            result.files_downloaded = [output_file]
            result.bytes_downloaded = output_file.stat().st_size

            logger.info(f"Downloaded {len(df)} batting records")

        except Exception as e:
            result.error = str(e)
            result.error_code = "DOWNLOAD_ERROR"
            logger.exception(f"Download failed: {e}")

        finally:
            result.end_time = datetime.now()

        return result

    def download_pitching_stats(
        self,
        season: int,
        qual: int = 0,
    ) -> DownloadResult:
        """Download pitching leaderboard.

        Args:
            season: Season year
            qual: Minimum innings pitched

        Returns:
            DownloadResult
        """
        result = DownloadResult(
            source=SourceType.FANGRAPHS,
            status=ResultStatus.FAILED,
        )
        result.start_time = datetime.now()

        try:
            logger.info(f"Downloading FanGraphs pitching stats for {season}")

            params = {
                "pos": "all",
                "stats": "pit",
                "lg": "all",
                "qual": qual,
                "type": 8,
                "season": season,
                "season1": season,
                "ind": 0,
                "csv": 1,
            }

            response = self.client.get(self.BASE_URL, params=params)
            response.raise_for_status()

            df = pd.read_csv(StringIO(response.text))

            output_file = self.output_dir / f"pitching_stats_{season}.csv"
            save_csv(df, output_file)

            result.status = ResultStatus.SUCCESS
            result.rows_downloaded = len(df)
            result.files_downloaded = [output_file]
            result.bytes_downloaded = output_file.stat().st_size

            logger.info(f"Downloaded {len(df)} pitching records")

        except Exception as e:
            result.error = str(e)
            result.error_code = "DOWNLOAD_ERROR"
            logger.exception(f"Download failed: {e}")

        finally:
            result.end_time = datetime.now()

        return result
