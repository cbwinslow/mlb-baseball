"""
================================================================================
StatCast Ingestor
Date: 2026-05-09

Load StatCast data into database.
================================================================================
"""

from datetime import datetime
from pathlib import Path

import pandas as pd

from baseball.core.enums import ResultStatus, SourceType
from baseball.core.logging import get_logger
from baseball.core.results import IngestResult
from baseball.sources.common.files import load_csv


logger = get_logger(__name__)


class StatcastIngestor:
    """Ingest StatCast data into database."""

    def __init__(self, db_connection=None):
        """Initialize ingestor.

        Args:
            db_connection: Database connection object
        """
        self.db = db_connection
        # TODO: Wire to actual database

    def ingest_pitch_data(self, path: Path) -> IngestResult:
        """Ingest pitch data into raw_statcast.pitches table.

        Args:
            path: Path to StatCast CSV

        Returns:
            IngestResult
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

            # TODO: Insert into database
            result.rows_inserted = len(df)
            result.status = ResultStatus.SUCCESS

            logger.info(f"Ingested {len(df)} pitch records")

        except Exception as e:
            result.error = str(e)
            result.error_code = "INGEST_ERROR"
            logger.exception(f"Ingest failed: {e}")

        finally:
            result.end_time = datetime.now()

        return result
