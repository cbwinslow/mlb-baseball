"""
================================================================================
StatCast Downloader
Date: 2026-05-09

Download StatCast pitch-level data via pybaseball wrapper.
================================================================================
"""

from datetime import date, datetime
from pathlib import Path

from baseball.core.enums import ResultStatus, SourceType
from baseball.core.logging import get_logger
from baseball.core.results import DownloadResult
from baseball.sources.common.files import save_csv

try:
    import pybaseball

    pybaseball.cache.enable()
    HAS_PYBASEBALL = True
except ImportError:
    HAS_PYBASEBALL = False


logger = get_logger(__name__)


class StatcastDownloader:
    """Download StatCast data via pybaseball."""

    def __init__(self, output_dir: Path = Path("data/raw/statcast")):
        """Initialize downloader.

        Args:
            output_dir: Output directory
        """
        if not HAS_PYBASEBALL:
            raise ImportError("pybaseball required for StatCast downloads")

        self.output_dir = Path(output_dir)

    def download_season(
        self,
        season: int,
    ) -> DownloadResult:
        """Download StatCast data for full season.

        Args:
            season: Season year

        Returns:
            DownloadResult
        """
        result = DownloadResult(
            source=SourceType.STATCAST,
            status=ResultStatus.FAILED,
        )
        result.start_time = datetime.now()

        try:
            logger.info(f"Downloading StatCast for {season}")

            # MLB season typically March 28 - November 5
            start = date(season, 3, 28)
            end = date(season, 11, 5)

            df = pybaseball.statcast(
                start_dt=str(start),
                end_dt=str(end),
            )

            if df is not None and not df.empty:
                output_file = self.output_dir / f"statcast_{season}.csv"
                save_csv(df, output_file)

                result.status = ResultStatus.SUCCESS
                result.rows_downloaded = len(df)
                result.files_downloaded = [output_file]
                result.bytes_downloaded = output_file.stat().st_size

                logger.info(f"Downloaded {len(df):,} pitches for {season}")
            else:
                result.error = "No data returned"

        except Exception as e:
            result.error = str(e)
            result.error_code = "DOWNLOAD_ERROR"
            logger.exception(f"Download failed: {e}")

        finally:
            result.end_time = datetime.now()

        return result

    def download_pitcher(
        self,
        pitcher_id: int,
        season: int | None = None,
    ) -> DownloadResult:
        """Download StatCast data for specific pitcher.

        Args:
            pitcher_id: Pitcher MLBAM ID
            season: Optional season year

        Returns:
            DownloadResult
        """
        result = DownloadResult(
            source=SourceType.STATCAST,
            status=ResultStatus.FAILED,
        )
        result.start_time = datetime.now()

        try:
            logger.info(f"Downloading StatCast for pitcher {pitcher_id}")

            df = pybaseball.statcast_pitcher(
                pitcher_id=pitcher_id,
                start_dt=str(date(season, 3, 1)) if season else None,
                end_dt=str(date(season, 11, 30)) if season else None,
            )

            if df is not None and not df.empty:
                season_str = f"_{season}" if season else ""
                output_file = (
                    self.output_dir / f"statcast_pitcher_{pitcher_id}{season_str}.csv"
                )
                save_csv(df, output_file)

                result.status = ResultStatus.SUCCESS
                result.rows_downloaded = len(df)
                result.files_downloaded = [output_file]
                result.bytes_downloaded = output_file.stat().st_size

                logger.info(f"Downloaded {len(df):,} pitches for pitcher {pitcher_id}")
            else:
                result.error = "No data returned"

        except Exception as e:
            result.error = str(e)
            result.error_code = "DOWNLOAD_ERROR"
            logger.exception(f"Download failed: {e}")

        finally:
            result.end_time = datetime.now()

        return result

    def download_batter(
        self,
        batter_id: int,
        season: int | None = None,
    ) -> DownloadResult:
        """Download StatCast data for specific batter.

        Args:
            batter_id: Batter MLBAM ID
            season: Optional season year

        Returns:
            DownloadResult
        """
        result = DownloadResult(
            source=SourceType.STATCAST,
            status=ResultStatus.FAILED,
        )
        result.start_time = datetime.now()

        try:
            logger.info(f"Downloading StatCast for batter {batter_id}")

            df = pybaseball.statcast_batter(
                batter_id=batter_id,
                start_dt=str(date(season, 3, 1)) if season else None,
                end_dt=str(date(season, 11, 30)) if season else None,
            )

            if df is not None and not df.empty:
                season_str = f"_{season}" if season else ""
                output_file = (
                    self.output_dir / f"statcast_batter_{batter_id}{season_str}.csv"
                )
                save_csv(df, output_file)

                result.status = ResultStatus.SUCCESS
                result.rows_downloaded = len(df)
                result.files_downloaded = [output_file]
                result.bytes_downloaded = output_file.stat().st_size

                logger.info(f"Downloaded {len(df):,} pitches for batter {batter_id}")
            else:
                result.error = "No data returned"

        except Exception as e:
            result.error = str(e)
            result.error_code = "DOWNLOAD_ERROR"
            logger.exception(f"Download failed: {e}")

        finally:
            result.end_time = datetime.now()

        return result
