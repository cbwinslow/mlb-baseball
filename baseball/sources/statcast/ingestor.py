"""
================================================================================
StatCast Ingestor
Date: 2026-05-09 (updated 2026-05-11)
Script: ingestor.py
Version: 2.0.0

Load StatCast CSV data into baseball.statcast_pitches.
CSV files are produced by StatcastDownloader (Baseball Savant export format).
Uses batch upserts with ON CONFLICT (game_pk, at_bat_number, pitch_number)
for full idempotency.

Inputs:  Statcast CSV files from Baseball Savant
Outputs: Rows upserted into baseball.statcast_pitches
================================================================================
"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.engine import Engine

from baseball.core.enums import ResultStatus, SourceType
from baseball.core.logging import get_logger
from baseball.core.results import IngestResult
from baseball.sources.common.files import load_csv

logger = get_logger(__name__)

# Batch size for bulk inserts
_BATCH_SIZE = 1000


class StatcastIngestor:
    """Ingest StatCast data into database."""

    def __init__(self, db_connection: Optional[Engine] = None) -> None:
        """Initialize ingestor.

        Args:
            db_connection: SQLAlchemy Engine. When None the ingestor operates
                in dry-run / validation mode and will not write to DB.
        """
        self.db = db_connection
        self._dry_run = db_connection is None
        if self._dry_run:
            logger.warning(
                "StatcastIngestor initialised without a DB connection – "
                "running in dry-run mode (no data will be written)"
            )

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
        return self._ingest_pitch_data(path, season=season)

    def ingest_pitcher(
        self,
        path: Path,
        pitcher_id: int,
        season: Optional[int] = None,
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
        return self._ingest_pitch_data(path, season=season)

    def ingest_batter(
        self,
        path: Path,
        batter_id: int,
        season: Optional[int] = None,
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
        return self._ingest_pitch_data(path, season=season)

    # ------------------------------------------------------------------
    # Core ingest logic
    # ------------------------------------------------------------------

    def _ingest_pitch_data(
        self,
        path: Path,
        season: Optional[int] = None,
    ) -> IngestResult:
        """Load a Statcast CSV and upsert all rows into statcast_pitches.

        Args:
            path: Path to the CSV file.
            season: Override season; if None, derived from game_date column.

        Returns:
            IngestResult with row counts and timing.
        """
        start = datetime.utcnow()
        rows_inserted = 0
        rows_skipped = 0
        error = None
        status = ResultStatus.FAILED

        try:
            if not path.exists():
                raise FileNotFoundError(f"Statcast file not found: {path}")

            raw_rows = load_csv(path)

            if raw_rows.empty:
                logger.warning("Statcast CSV is empty: %s", path)
                return IngestResult(
                    source=SourceType.STATCAST,
                    status=ResultStatus.SUCCESS,
                    rows_inserted=0,
                    rows_skipped=0,
                    start_time=start,
                    end_time=datetime.utcnow(),
                )

            params = [
                self._map_pitch_row(row, season) for _, row in raw_rows.iterrows()
            ]

            if self._dry_run:
                logger.info(
                    "[dry-run] Would ingest %d Statcast pitches from %s",
                    len(params),
                    path,
                )
                rows_inserted = len(params)
            else:
                rows_inserted, rows_skipped = self._bulk_upsert_pitches(params)

            status = ResultStatus.SUCCESS
            logger.info(
                "Statcast ingest complete: %d inserted, %d skipped from %s",
                rows_inserted,
                rows_skipped,
                path,
            )

        except Exception as exc:
            logger.exception("Statcast ingest failed for %s: %s", path, exc)
            error = str(exc)

        return IngestResult(
            source=SourceType.STATCAST,
            status=status,
            rows_inserted=rows_inserted,
            rows_skipped=rows_skipped,
            start_time=start,
            end_time=datetime.utcnow(),
            error=error,
        )

    # ------------------------------------------------------------------
    # DB write helpers
    # ------------------------------------------------------------------

    def _bulk_upsert_pitches(
        self, params: list[dict[str, Any]]
    ) -> tuple[int, int]:
        """Bulk-upsert pitch rows into baseball.statcast_pitches.

        Uses ON CONFLICT (game_pk, at_bat_number, pitch_number) DO UPDATE.
        Processes in batches of _BATCH_SIZE.

        Returns:
            Tuple of (rows_upserted, rows_skipped).
        """
        upsert_sql = text("""
            INSERT INTO baseball.statcast_pitches (
                game_pk, game_date, season, game_type,
                at_bat_number, pitch_number, inning, inning_topbot,
                pitcher_id, pitcher_name, p_throws,
                batter_id, batter_name, stand,
                pitch_type, pitch_name,
                release_speed, release_spin_rate, release_extension,
                pfx_x, pfx_z, plate_x, plate_z, sz_top, sz_bot,
                launch_speed, launch_angle, hit_distance_sc, hc_x, hc_y,
                hit_location,
                description, events, type, bb_type,
                balls, strikes, outs_when_up,
                on_1b, on_2b, on_3b,
                estimated_ba_using_speedangle,
                estimated_woba_using_speedangle,
                woba_value, woba_denom, babip_value, iso_value,
                home_team, away_team
            ) VALUES (
                :game_pk, :game_date, :season, :game_type,
                :at_bat_number, :pitch_number, :inning, :inning_topbot,
                :pitcher_id, :pitcher_name, :p_throws,
                :batter_id, :batter_name, :stand,
                :pitch_type, :pitch_name,
                :release_speed, :release_spin_rate, :release_extension,
                :pfx_x, :pfx_z, :plate_x, :plate_z, :sz_top, :sz_bot,
                :launch_speed, :launch_angle, :hit_distance_sc, :hc_x, :hc_y,
                :hit_location,
                :description, :events, :type, :bb_type,
                :balls, :strikes, :outs_when_up,
                :on_1b, :on_2b, :on_3b,
                :estimated_ba_using_speedangle,
                :estimated_woba_using_speedangle,
                :woba_value, :woba_denom, :babip_value, :iso_value,
                :home_team, :away_team
            )
            ON CONFLICT (game_pk, at_bat_number, pitch_number) DO UPDATE SET
                release_speed    = EXCLUDED.release_speed,
                release_spin_rate = EXCLUDED.release_spin_rate,
                launch_speed     = EXCLUDED.launch_speed,
                launch_angle     = EXCLUDED.launch_angle,
                hit_distance_sc  = EXCLUDED.hit_distance_sc,
                description      = EXCLUDED.description,
                events           = EXCLUDED.events,
                woba_value       = EXCLUDED.woba_value,
                woba_denom       = EXCLUDED.woba_denom,
                estimated_ba_using_speedangle  = EXCLUDED.estimated_ba_using_speedangle,
                estimated_woba_using_speedangle = EXCLUDED.estimated_woba_using_speedangle
        """)

        total = 0
        with self.db.connect() as conn:
            for i in range(0, len(params), _BATCH_SIZE):
                batch = params[i : i + _BATCH_SIZE]
                conn.execute(upsert_sql, batch)
                total += len(batch)
            conn.commit()

        logger.debug("_bulk_upsert_pitches: wrote %d rows", total)
        return total, 0

    # ------------------------------------------------------------------
    # Row mapping
    # ------------------------------------------------------------------

    @staticmethod
    def _map_pitch_row(
        row: dict[str, Any],
        season_override: Optional[int] = None,
    ) -> dict[str, Any]:
        """Normalise a raw Statcast CSV row into a DB params dict."""

        def _float(val: Any) -> Optional[float]:
            try:
                return float(val) if val not in (None, "", "null") else None
            except (TypeError, ValueError):
                return None

        def _int(val: Any) -> Optional[int]:
            try:
                return int(float(val)) if val not in (None, "", "null") else None
            except (TypeError, ValueError):
                return None

        def _str(val: Any, maxlen: int = 64) -> Optional[str]:
            s = str(val).strip() if val not in (None, "", "null") else None
            return s[:maxlen] if s else None

        # Derive season from game_date if not overridden
        game_date = _str(row.get("game_date"), 10)
        season = season_override
        if season is None and game_date:
            try:
                season = int(game_date[:4])
            except (ValueError, TypeError):
                season = None

        return {
            "game_pk": _int(row.get("game_pk")),
            "game_date": game_date,
            "season": season,
            "game_type": _str(row.get("game_type"), 2),
            "at_bat_number": _int(row.get("at_bat_number")),
            "pitch_number": _int(row.get("pitch_number")),
            "inning": _int(row.get("inning")),
            "inning_topbot": _str(row.get("inning_topbot"), 3),
            "pitcher_id": _int(row.get("pitcher")),
            "pitcher_name": _str(row.get("player_name"), 64),
            "p_throws": _str(row.get("p_throws"), 1),
            "batter_id": _int(row.get("batter")),
            "batter_name": _str(row.get("batter_name"), 64),
            "stand": _str(row.get("stand"), 1),
            "pitch_type": _str(row.get("pitch_type"), 4),
            "pitch_name": _str(row.get("pitch_name"), 32),
            "release_speed": _float(row.get("release_speed")),
            "release_spin_rate": _int(row.get("release_spin_rate")),
            "release_extension": _float(row.get("release_extension")),
            "pfx_x": _float(row.get("pfx_x")),
            "pfx_z": _float(row.get("pfx_z")),
            "plate_x": _float(row.get("plate_x")),
            "plate_z": _float(row.get("plate_z")),
            "sz_top": _float(row.get("sz_top")),
            "sz_bot": _float(row.get("sz_bot")),
            "launch_speed": _float(row.get("launch_speed")),
            "launch_angle": _float(row.get("launch_angle")),
            "hit_distance_sc": _float(row.get("hit_distance_sc")),
            "hc_x": _float(row.get("hc_x")),
            "hc_y": _float(row.get("hc_y")),
            "hit_location": _int(row.get("hit_location")),
            "description": _str(row.get("description"), 64),
            "events": _str(row.get("events"), 64),
            "type": _str(row.get("type"), 1),
            "bb_type": _str(row.get("bb_type"), 32),
            "balls": _int(row.get("balls")),
            "strikes": _int(row.get("strikes")),
            "outs_when_up": _int(row.get("outs_when_up")),
            "on_1b": _int(row.get("on_1b")),
            "on_2b": _int(row.get("on_2b")),
            "on_3b": _int(row.get("on_3b")),
            "estimated_ba_using_speedangle": _float(
                row.get("estimated_ba_using_speedangle")
            ),
            "estimated_woba_using_speedangle": _float(
                row.get("estimated_woba_using_speedangle")
            ),
            "woba_value": _float(row.get("woba_value")),
            "woba_denom": _int(row.get("woba_denom")),
            "babip_value": _float(row.get("babip_value")),
            "iso_value": _float(row.get("iso_value")),
            "home_team": _str(row.get("home_team"), 4),
            "away_team": _str(row.get("away_team"), 4),
        }
