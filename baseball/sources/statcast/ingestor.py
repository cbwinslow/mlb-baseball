"""
================================================================================
StatCast Ingestor
Date: 2026-05-09 (updated 2026-05-11)

Load StatCast data into database.
================================================================================
"""

from datetime import datetime
from pathlib import Path


from baseball.core.enums import ResultStatus, SourceType
from baseball.core.logging import get_logger
from baseball.core.results import IngestResult
from baseball.sources.common.files import load_csv

logger = get_logger(__name__)


class StatcastIngestor:
    """Ingest StatCast data into database."""

    def __init__(self, db_connection=None):
        """
        Args:
            db_connection: Database connection or URL string.  When None the
                ingestor operates in dry-run / validation mode.
        """
        self.db = db_connection  # TODO: Wire to actual database

    # ------------------------------------------------------------------
    # Primary public API (used by CLI)
    # ------------------------------------------------------------------

    def ingest_season(
        self,
        path: Path,
        season: int,
    ) -> IngestResult:
        """Ingest a full StatCast season CSV file.

        Args:
            path: Path to the StatCast CSV produced by StatcastDownloader.
            season: Season year (used for logging/tagging only).

        Returns:
            IngestResult with row counts and timing.
        """
        logger.info("Ingesting StatCast season %s from %s", season, path)
        result = self.ingest_pitch_data(path)
        return result

    def ingest_pitcher(
        self,
        path: Path,
        pitcher_id: int,
        season: int | None = None,
    ) -> IngestResult:
        """Ingest a StatCast pitcher CSV file.

        Args:
            path: Path to the pitcher StatCast CSV.
            pitcher_id: MLB pitcher ID (for logging context).
            season: Optional season year.

        Returns:
            IngestResult with row counts and timing.
        """
        logger.info(
            "Ingesting StatCast pitcher %s season %s from %s",
            pitcher_id,
            season,
            path,
        )
        result = self.ingest_pitch_data(path)
        return result

    def ingest_batter(
        self,
        path: Path,
        batter_id: int,
        season: int | None = None,
    ) -> IngestResult:
        """Ingest a StatCast batter CSV file.

        Args:
            path: Path to the batter StatCast CSV.
            batter_id: MLB batter ID (for logging context).
            season: Optional season year.

        Returns:
            IngestResult with row counts and timing.
        """
        logger.info(
            "Ingesting StatCast batter %s season %s from %s",
            batter_id,
            season,
            path,
        )
        result = self.ingest_pitch_data(path)
        return result

    # ------------------------------------------------------------------
    # Core implementation
    # ------------------------------------------------------------------

    def ingest_pitch_data(self, path: Path) -> IngestResult:
        """Ingest pitch data CSV into raw_statcast.pitches table.

        Args:
            path: Path to any StatCast CSV file.

        Returns:
            IngestResult with row counts and timing.
        """
        result = IngestResult(
            source=SourceType.STATCAST,
            status=ResultStatus.FAILED,
            staging_table="staging_statcast_pitches",
            raw_table="raw_statcast.pitches",
        )
        result.start_time = datetime.now()
        try:
            df = load_csv(path)
            # TODO: Insert df into database once schema is finalised
            result.rows_inserted = len(df)
            result.status = ResultStatus.SUCCESS
            logger.info("Ingested %d pitch records from %s", len(df), path)
        except Exception as exc:
            result.error = str(exc)
            result.error_code = "INGEST_ERROR"
            logger.exception("StatCast ingest failed: %s", exc)
        finally:
            result.end_time = datetime.now()
        return result
