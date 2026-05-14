"""
================================================================================
Retrosheet Ingestor
Date: 2026-05-09 (updated 2026-05-11)
Script: ingestor.py
Version: 2.0.0

Load Retrosheet event files into baseball.retro_events.
Uses the existing RetroEventFileParser to iterate over plays, then bulk-upserts
into the database using ON CONFLICT (game_id, event_id) DO UPDATE.

Inputs:  Retrosheet .EVA / .EVN event files
Outputs: Rows upserted into baseball.retro_events
================================================================================
"""

from __future__ import annotations

from datetime import datetime, date
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.engine import Engine

from baseball.core.enums import ResultStatus, SourceType
from baseball.core.logging import get_logger
from baseball.core.results import IngestResult
from baseball.sources.retrosheet.parser import RetroEventFileParser

logger = get_logger(__name__)

# Batch size for bulk upserts – keeps memory bounded on large event files
_BATCH_SIZE = 500

# Retrosheet event code -> hit_val mapping
_HIT_VAL: dict[int, int] = {20: 1, 21: 2, 22: 3, 23: 4}  # S, D, T, HR


class RetroEventFileIngestor:
    """Ingest Retrosheet event files into database."""

    def __init__(self, db_connection: Optional[Engine] = None) -> None:
        """Initialize ingestor.

        Args:
            db_connection: SQLAlchemy Engine. When None operates in dry-run mode.
        """
        self.db = db_connection
        self._dry_run = db_connection is None
        self.parser = RetroEventFileParser()
        if self._dry_run:
            logger.warning(
                "RetroEventFileIngestor initialised without a DB connection – "
                "running in dry-run mode (no data will be written)"
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def ingest_event_file(
        self,
        path: Path,
        season: int,
    ) -> IngestResult:
        """Ingest a Retrosheet event file (.EVA/.EVN) into retro_events.

        Args:
            path: Path to the Retrosheet event file.
            season: Season year.

        Returns:
            IngestResult with row counts and timing.
        """
        result = IngestResult(
            source=SourceType.RETROSHEET,
            status=ResultStatus.FAILED,
        )
        result.start_time = datetime.utcnow()

        try:
            logger.info("Ingesting Retrosheet event file: %s (season=%s)", path, season)

            events: list[dict] = []
            event_id = 0
            for event in self.parser.parse_file(path):
                event_id += 1
                events.append(self._build_event_row(event, event_id, season, path))

            if self._dry_run:
                logger.info(
                    "[dry-run] Would ingest %d events from %s (season=%s)",
                    len(events),
                    path,
                    season,
                )
                result.rows_inserted = len(events)
            else:
                inserted, skipped = self._bulk_upsert_events(events)
                result.rows_inserted = inserted
                result.rows_skipped = skipped

            result.status = ResultStatus.SUCCESS
            logger.info(
                "Retrosheet ingest complete: %d events from %s",
                len(events),
                path,
            )

        except Exception as exc:
            result.error = str(exc)
            logger.exception("Retrosheet ingest failed for %s: %s", path, exc)
        finally:
            result.end_time = datetime.utcnow()

        return result

    def ingest_game_logs(
        self,
        path: Path,
        season: int,
        league: str = "MLB",
    ) -> IngestResult:
        """Ingest a Retrosheet game log file (GLyyyy.TXT).

        Game logs contain one line per game with ~160 comma-separated fields.
        We store the raw line in retro_events with event_type=0 (game log marker)
        so the data is preserved without full field parsing.

        Args:
            path: Path to the game log file.
            season: Season year.
            league: League identifier string.

        Returns:
            IngestResult with row counts and timing.
        """
        result = IngestResult(
            source=SourceType.RETROSHEET,
            status=ResultStatus.FAILED,
        )
        result.start_time = datetime.utcnow()

        try:
            logger.info("Ingesting game log file: %s (season=%s)", path, season)

            if not path.exists():
                raise FileNotFoundError(f"Game log file not found: {path}")

            rows: list[dict] = []
            with open(path, encoding="utf-8", errors="replace") as fh:
                for line_no, line in enumerate(fh, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    fields = line.split(",")
                    game_id = fields[0].strip('"') if fields else f"GL{season}{line_no:05d}"
                    rows.append({
                        "game_id": game_id,
                        "season": season,
                        "game_date": self._parse_game_log_date(fields),
                        "home_team": fields[6].strip('"') if len(fields) > 6 else "",
                        "visiting_team": fields[3].strip('"') if len(fields) > 3 else "",
                        "event_id": line_no,
                        "inning": 9,
                        "batting_team": "0",
                        "outs": 3,
                        "batter_id": "unknown",
                        "pitcher_id": "unknown",
                        "play_text": "GAMELOG",
                        "event_type": 0,
                        "rbi_ct": 0,
                        "runs_scored": 0,
                        "sh_fl": False,
                        "sf_fl": False,
                        "dp_fl": False,
                        "tp_fl": False,
                        "wp_fl": False,
                        "pb_fl": False,
                        "source_file": path.name,
                        "raw_line": line[:2000],
                    })

            if self._dry_run:
                logger.info("[dry-run] Would ingest %d game log rows", len(rows))
                result.rows_inserted = len(rows)
            else:
                inserted, skipped = self._bulk_upsert_events(rows)
                result.rows_inserted = inserted
                result.rows_skipped = skipped

            result.status = ResultStatus.SUCCESS
            logger.info(
                "Game log ingest complete: %d rows from %s", len(rows), path
            )

        except Exception as exc:
            result.error = str(exc)
            logger.exception("Game log ingest failed for %s: %s", path, exc)
        finally:
            result.end_time = datetime.utcnow()

        return result

    # ------------------------------------------------------------------
    # Private helpers – DB writes
    # ------------------------------------------------------------------

    def _bulk_upsert_events(
        self, events: list[dict[str, Any]]
    ) -> tuple[int, int]:
        """Bulk-upsert event rows into baseball.retro_events.

        Processes in batches of _BATCH_SIZE to avoid huge parameter lists.
        Uses ON CONFLICT (game_id, event_id) DO UPDATE for idempotency.

        Returns:
            Tuple of (rows_inserted_or_updated, rows_skipped).
        """
        upsert_sql = text("""
            INSERT INTO baseball.retro_events (
                game_id, season, game_date, home_team, visiting_team,
                event_id, inning, batting_team, outs,
                batter_id, pitcher_id, batter_hand, pitcher_hand,
                balls, strikes,
                runner_on_1b, runner_on_2b, runner_on_3b,
                play_text, event_type, event_cd, hit_val,
                batted_ball_type, hit_location,
                rbi_ct, runs_scored, fielded_by,
                sh_fl, sf_fl, dp_fl, tp_fl, wp_fl, pb_fl,
                source_file, raw_line
            ) VALUES (
                :game_id, :season, :game_date, :home_team, :visiting_team,
                :event_id, :inning, :batting_team, :outs,
                :batter_id, :pitcher_id, :batter_hand, :pitcher_hand,
                :balls, :strikes,
                :runner_on_1b, :runner_on_2b, :runner_on_3b,
                :play_text, :event_type, :event_cd, :hit_val,
                :batted_ball_type, :hit_location,
                :rbi_ct, :runs_scored, :fielded_by,
                :sh_fl, :sf_fl, :dp_fl, :tp_fl, :wp_fl, :pb_fl,
                :source_file, :raw_line
            )
            ON CONFLICT (game_id, event_id) DO UPDATE SET
                season         = EXCLUDED.season,
                game_date      = EXCLUDED.game_date,
                play_text      = EXCLUDED.play_text,
                event_type     = EXCLUDED.event_type,
                event_cd       = EXCLUDED.event_cd,
                hit_val        = EXCLUDED.hit_val,
                rbi_ct         = EXCLUDED.rbi_ct,
                runs_scored    = EXCLUDED.runs_scored,
                raw_line       = EXCLUDED.raw_line
        """)

        total_written = 0
        with self.db.connect() as conn:
            for i in range(0, len(events), _BATCH_SIZE):
                batch = events[i : i + _BATCH_SIZE]
                conn.execute(upsert_sql, batch)
                total_written += len(batch)
            conn.commit()

        logger.debug(
            "_bulk_upsert_events: wrote %d rows in %d batch(es)",
            total_written,
            (len(events) + _BATCH_SIZE - 1) // _BATCH_SIZE,
        )
        return total_written, 0

    # ------------------------------------------------------------------
    # Internal utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _build_event_row(
        event: dict[str, Any],
        event_id: int,
        season: int,
        source_path: Path,
    ) -> dict[str, Any]:
        """Convert a parsed Retrosheet event dict into a DB params dict."""
        def _bool(val: Any) -> bool:
            return bool(val) if val not in (None, "", "0", 0) else False

        def _int_or_none(val: Any) -> Optional[int]:
            try:
                return int(val) if val not in (None, "") else None
            except (TypeError, ValueError):
                return None

        return {
            "game_id": str(event.get("game_id", ""))[:12],
            "season": season,
            "game_date": event.get("game_date") or None,
            "home_team": str(event.get("home_team", ""))[:3],
            "visiting_team": str(event.get("visiting_team", ""))[:3],
            "event_id": event_id,
            "inning": _int_or_none(event.get("inning")) or 1,
            "batting_team": str(event.get("batting_team", "0"))[:1],
            "outs": _int_or_none(event.get("outs")) or 0,
            "batter_id": str(event.get("batter_id", "unknown"))[:8],
            "pitcher_id": str(event.get("pitcher_id", "unknown"))[:8],
            "batter_hand": str(event.get("batter_hand", ""))[:1] or None,
            "pitcher_hand": str(event.get("pitcher_hand", ""))[:1] or None,
            "balls": _int_or_none(event.get("balls")),
            "strikes": _int_or_none(event.get("strikes")),
            "runner_on_1b": str(event.get("runner_on_1b", ""))[:8] or None,
            "runner_on_2b": str(event.get("runner_on_2b", ""))[:8] or None,
            "runner_on_3b": str(event.get("runner_on_3b", ""))[:8] or None,
            "play_text": str(event.get("play_text", ""))[:64],
            "event_type": _int_or_none(event.get("event_type")),
            "event_cd": _int_or_none(event.get("event_cd")),
            "hit_val": _HIT_VAL.get(
                _int_or_none(event.get("event_type")) or 0, 0
            ),
            "batted_ball_type": str(event.get("batted_ball_type", ""))[:4] or None,
            "hit_location": _int_or_none(event.get("hit_location")),
            "rbi_ct": _int_or_none(event.get("rbi_ct")) or 0,
            "runs_scored": _int_or_none(event.get("runs_scored")) or 0,
            "fielded_by": _int_or_none(event.get("fielded_by")),
            "sh_fl": _bool(event.get("sh_fl")),
            "sf_fl": _bool(event.get("sf_fl")),
            "dp_fl": _bool(event.get("dp_fl")),
            "tp_fl": _bool(event.get("tp_fl")),
            "wp_fl": _bool(event.get("wp_fl")),
            "pb_fl": _bool(event.get("pb_fl")),
            "source_file": source_path.name[:32],
            "raw_line": str(event.get("raw_line", ""))[:2000] or None,
        }

    @staticmethod
    def _parse_game_log_date(fields: list[str]) -> Optional[date]:
        """Parse date from game log fields[0] format YYYYMMDD."""
        try:
            raw = fields[0].strip('"')
            return datetime.strptime(raw, "%Y%m%d").date()
        except (ValueError, IndexError):
            return None
