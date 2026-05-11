"""
================================================================================
MLB StatsAPI Ingestor
Date: 2026-05-11
Script: ingestor.py
Version: 2.0.0

Load MLB StatsAPI downloaded JSON/CSV files into the database.
Supports dry-run mode when no DB connection is provided.

Inputs:  CSV/JSON files produced by MLBDownloader
Outputs: Rows upserted into baseball.mlb_schedule
================================================================================
"""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import text
from sqlalchemy.engine import Engine

from baseball.core.enums import ResultStatus, SourceType
from baseball.core.logging import get_logger
from baseball.core.results import IngestResult

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Column mapping: CSV header -> DB column (baseball.mlb_schedule)
# Keys are lowercased CSV headers; values are DB column names.
# Only columns present in the CSV need to be listed here.
# ---------------------------------------------------------------------------
_SCHEDULE_COL_MAP: dict[str, str] = {
    "game_pk": "game_pk",
    "game_date": "game_date",
    "game_type": "game_type",
    "status": "status",
    "home_team_id": "home_team_id",
    "home_team_name": "home_team_name",
    "away_team_id": "away_team_id",
    "away_team_name": "away_team_name",
    "venue_id": "venue_id",
    "venue_name": "venue_name",
    "home_score": "home_score",
    "away_score": "away_score",
    "inning": "inning",
    "double_header": "double_header",
    "day_night": "day_night",
    "series_description": "series_description",
    "series_game_number": "series_game_number",
    "games_in_series": "games_in_series",
}


class MLBIngestor:
    """Ingest MLB StatsAPI data into the database."""

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
                "MLBIngestor initialised without a DB connection – "
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
                rows_inserted, rows_skipped = self._upsert_schedule_rows(rows, season)

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

        The JSON structure is the raw boxscore/linescore payload from the
        MLB StatsAPI.  We pull the liveData.linescore sub-tree and update
        the matching row in baseball.mlb_schedule.

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
    # Private helpers – DB writes
    # ------------------------------------------------------------------

    def _upsert_schedule_rows(
        self, rows: list[dict], season: int
    ) -> tuple[int, int]:
        """Insert or update schedule rows in baseball.mlb_schedule.

        Uses PostgreSQL INSERT ... ON CONFLICT (game_pk) DO UPDATE so that
        re-running an ingest for the same season is always idempotent.

        Args:
            rows: List of dicts from csv.DictReader.
            season: Season year to stamp on every row.

        Returns:
            Tuple of (rows_inserted, rows_skipped).  Because ON CONFLICT DO
            UPDATE always writes, we count all rows as inserted and skip=0.
        """
        upsert_sql = text("""
            INSERT INTO baseball.mlb_schedule (
                game_pk, season, game_date, game_type, status,
                home_team_id, home_team_name,
                away_team_id, away_team_name,
                venue_id, venue_name,
                home_score, away_score, inning,
                double_header, day_night,
                series_description, series_game_number, games_in_series
            ) VALUES (
                :game_pk, :season, :game_date, :game_type, :status,
                :home_team_id, :home_team_name,
                :away_team_id, :away_team_name,
                :venue_id, :venue_name,
                :home_score, :away_score, :inning,
                :double_header, :day_night,
                :series_description, :series_game_number, :games_in_series
            )
            ON CONFLICT (game_pk) DO UPDATE SET
                season             = EXCLUDED.season,
                game_date          = EXCLUDED.game_date,
                game_type          = EXCLUDED.game_type,
                status             = EXCLUDED.status,
                home_team_id       = EXCLUDED.home_team_id,
                home_team_name     = EXCLUDED.home_team_name,
                away_team_id       = EXCLUDED.away_team_id,
                away_team_name     = EXCLUDED.away_team_name,
                venue_id           = EXCLUDED.venue_id,
                venue_name         = EXCLUDED.venue_name,
                home_score         = EXCLUDED.home_score,
                away_score         = EXCLUDED.away_score,
                inning             = EXCLUDED.inning,
                double_header      = EXCLUDED.double_header,
                day_night          = EXCLUDED.day_night,
                series_description = EXCLUDED.series_description,
                series_game_number = EXCLUDED.series_game_number,
                games_in_series    = EXCLUDED.games_in_series,
                updated_at         = now()
        """)

        params = [self._map_schedule_row(row, season) for row in rows]

        with self.db_connection.connect() as conn:
            conn.execute(upsert_sql, params)
            conn.commit()

        logger.debug("_upsert_schedule_rows: wrote %d rows for season %s", len(rows), season)
        return len(rows), 0

    def _upsert_game_rows(
        self, data: dict, game_pk: int, season: int
    ) -> tuple[int, int]:
        """Update score/status fields on an existing mlb_schedule row.

        Pulls the liveData.linescore sub-tree from the StatsAPI game JSON
        and patches the matching game_pk row.  If the row does not yet exist
        (e.g. schedule was never ingested) we skip gracefully.

        Args:
            data: Parsed StatsAPI game JSON.
            game_pk: MLB game primary key.
            season: Season year.

        Returns:
            (1, 0) on update, (0, 1) if row not found.
        """
        linescore = (
            data.get("liveData", {})
            .get("linescore", {})
        )
        home_score = linescore.get("teams", {}).get("home", {}).get("runs")
        away_score = linescore.get("teams", {}).get("away", {}).get("runs")
        current_inning = linescore.get("currentInning")
        game_status = (
            data.get("gameData", {})
            .get("status", {})
            .get("detailedState", "unknown")
        )

        update_sql = text("""
            UPDATE baseball.mlb_schedule
            SET
                home_score = :home_score,
                away_score = :away_score,
                inning     = :inning,
                status     = :status,
                raw_json   = :raw_json,
                updated_at = now()
            WHERE game_pk = :game_pk
        """)

        with self.db_connection.connect() as conn:
            result = conn.execute(
                update_sql,
                {
                    "home_score": home_score,
                    "away_score": away_score,
                    "inning": current_inning,
                    "status": game_status,
                    "raw_json": json.dumps(data),
                    "game_pk": game_pk,
                },
            )
            conn.commit()
            rows_affected = result.rowcount

        if rows_affected == 0:
            logger.warning(
                "_upsert_game_rows: game_pk=%s not found in mlb_schedule – skipped",
                game_pk,
            )
            return 0, 1

        logger.debug("_upsert_game_rows: updated game_pk=%s", game_pk)
        return 1, 0

    # ------------------------------------------------------------------
    # Internal utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _map_schedule_row(row: dict, season: int) -> dict:
        """Normalise a raw CSV row dict into a params dict for the upsert."""
        def _int_or_none(val: str) -> Optional[int]:
            try:
                return int(val) if val not in ("", None) else None
            except (ValueError, TypeError):
                return None

        return {
            "game_pk": int(row.get("game_pk", 0)),
            "season": season,
            "game_date": row.get("game_date") or None,
            "game_type": row.get("game_type", "R")[:2],
            "status": row.get("status", "scheduled")[:32],
            "home_team_id": _int_or_none(row.get("home_team_id")),
            "home_team_name": (row.get("home_team_name") or "")[:64] or None,
            "away_team_id": _int_or_none(row.get("away_team_id")),
            "away_team_name": (row.get("away_team_name") or "")[:64] or None,
            "venue_id": _int_or_none(row.get("venue_id")),
            "venue_name": (row.get("venue_name") or "")[:128] or None,
            "home_score": _int_or_none(row.get("home_score")),
            "away_score": _int_or_none(row.get("away_score")),
            "inning": _int_or_none(row.get("inning")),
            "double_header": (row.get("double_header") or "N")[:1],
            "day_night": (row.get("day_night") or "")[:5] or None,
            "series_description": (row.get("series_description") or "")[:64] or None,
            "series_game_number": _int_or_none(row.get("series_game_number")),
            "games_in_series": _int_or_none(row.get("games_in_series")),
        }
