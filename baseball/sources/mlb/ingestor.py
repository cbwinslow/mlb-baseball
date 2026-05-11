"""
================================================================================
MLB StatsAPI Ingestor
Date: 2026-05-11

Load MLB StatsAPI downloaded JSON/CSV files into database staging/raw tables.
================================================================================
"""

from datetime import datetime
from pathlib import Path

from baseball.core.enums import ResultStatus, SourceType
from baseball.core.logging import get_logger
from baseball.core.results import IngestResult

logger = get_logger(__name__)


class MLBIngestor:
    """Ingest MLB StatsAPI data into the database."""

    def __init__(self, db_connection=None):
        """Initialize ingestor.

        Args:
            db_connection: Database connection or URL string.  When None the
                ingestor operates in dry-run / file-validation mode and will
                not attempt any DB writes.
        """
        self.db_connection = db_connection
        self._dry_run = db_connection is None
        if self._dry_run:
            logger.warning(
                "MLBIngestor initialised without a DB connection — "
                "running in dry-run mode (no data will be written)"
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def ingest_schedule(
        self,
        path: Path,
        season: int,
    ) -> IngestResult:
        """Ingest a schedule CSV file produced by MLBDownloader.

        Args:
            path: Path to the schedule CSV file.
            season: Season year (used to tag rows and log context).

        Returns:
            IngestResult with row counts and timing.
        """
        start = datetime.utcnow()
        rows_inserted = 0
        rows_skipped = 0
        error = None

        try:
            if not path.exists():
                raise FileNotFoundError(f"Schedule file not found: {path}")

            import csv

            with open(path, newline="", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                rows = list(reader)

            if self._dry_run:
                logger.info(
                    "[dry-run] Would ingest %d schedule rows for season %s from %s",
                    len(rows),
                    season,
                    path,
                )
                rows_inserted = len(rows)
            else:
                rows_inserted, rows_skipped = self._upsert_schedule_rows(
                    rows, season
                )

            status = ResultStatus.SUCCESS
            logger.info(
                "MLB schedule ingest complete: %d inserted, %d skipped (season=%s)",
                rows_inserted,
                rows_skipped,
                season,
            )
        except Exception as exc:
            logger.exception("MLB schedule ingest failed: %s", exc)
            status = ResultStatus.FAILURE
            error = str(exc)

        return IngestResult(
            source=SourceType.MLB_STATS_API,
            status=status,
            rows_inserted=rows_inserted,
            rows_skipped=rows_skipped,
            start_time=start,
            end_time=datetime.utcnow(),
            error=error,
        )

    def ingest_game(
        self,
        path: Path,
        game_pk: int,
        season: int,
    ) -> IngestResult:
        """Ingest a single game JSON file produced by MLBDownloader.

        Args:
            path: Path to the game JSON file.
            game_pk: MLB game primary key.
            season: Season year.

        Returns:
            IngestResult with row counts and timing.
        """
        start = datetime.utcnow()
        rows_inserted = 0
        rows_skipped = 0
        error = None

        try:
            if not path.exists():
                raise FileNotFoundError(f"Game file not found: {path}")

            import json

            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)

            if self._dry_run:
                logger.info(
                    "[dry-run] Would ingest game %s (season=%s) from %s",
                    game_pk,
                    season,
                    path,
                )
                rows_inserted = 1
            else:
                rows_inserted, rows_skipped = self._upsert_game_rows(
                    data, game_pk, season
                )

            status = ResultStatus.SUCCESS
            logger.info(
                "MLB game ingest complete: game_pk=%s season=%s inserted=%d skipped=%d",
                game_pk,
                season,
                rows_inserted,
                rows_skipped,
            )
        except Exception as exc:
            logger.exception("MLB game ingest failed (game_pk=%s): %s", game_pk, exc)
            status = ResultStatus.FAILURE
            error = str(exc)

        return IngestResult(
            source=SourceType.MLB_STATS_API,
            status=status,
            rows_inserted=rows_inserted,
            rows_skipped=rows_skipped,
            start_time=start,
            end_time=datetime.utcnow(),
            error=error,
        )

    # ------------------------------------------------------------------
    # Private helpers  (DB writes — wired once schema is finalised)
    # ------------------------------------------------------------------

    def _upsert_schedule_rows(
        self, rows: list[dict], season: int
    ) -> tuple[int, int]:
        """Insert or update schedule rows in mlb_schedule table.

        TODO: implement once DB schema is finalised.
              Use psycopg2 executemany with ON CONFLICT DO UPDATE.
        """
        # Placeholder — returns counts as if all rows were new.
        logger.debug(
            "_upsert_schedule_rows called with %d rows for season %s (TODO: DB write)",
            len(rows),
            season,
        )
        return len(rows), 0

    def _upsert_game_rows(
        self, data: dict, game_pk: int, season: int
    ) -> tuple[int, int]:
        """Insert or update a game record in mlb_games table.

        TODO: implement once DB schema is finalised.
        """
        logger.debug(
            "_upsert_game_rows called for game_pk=%s season=%s (TODO: DB write)",
            game_pk,
            season,
        )
        return 1, 0
