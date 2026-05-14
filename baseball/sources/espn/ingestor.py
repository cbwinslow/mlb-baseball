"""
================================================================================
ESPN Ingestor
Date: 2026-05-13
Script: ingestor.py
Version: 1.0.0

Load ESPN downloaded JSON files into the database.
Supports dry-run mode when no DB connection is provided.

Inputs:  JSON files produced by ESPNDownloader
Outputs: Rows upserted into raw.espn_* tables
================================================================================
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.engine import Engine

from baseball.core.enums import ResultStatus, SourceType
from baseball.core.logging import get_logger
from baseball.core.results import IngestResult

logger = get_logger(__name__)


class ESPNIngestor:
    """Ingest ESPN data into the database."""

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
                "ESPNIngestor initialised without a DB connection – "
                "running in dry-run mode (no data will be written)"
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def ingest_scoreboard(
        self,
        path: Path,
    ) -> IngestResult:
        """Ingest a scoreboard JSON file produced by ESPNDownloader.

        Args:
            path: Path to the scoreboard JSON file.

        Returns:
            IngestResult with row counts and timing.
        """
        start = datetime.utcnow()
        events_inserted = 0
        competitions_inserted = 0
        teams_inserted = 0
        venues_inserted = 0
        broadcasts_inserted = 0
        odds_inserted = 0
        error = None

        try:
            if not path.exists():
                raise FileNotFoundError(f"Scoreboard file not found: {path}")

            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)

            if self._dry_run:
                logger.info(
                    "[dry-run] Would ingest scoreboard data from %s",
                    path,
                )
                # Count what would be inserted
                events = data.get("events", [])
                events_inserted = len(events)
                for event in events:
                    competitions_inserted += len(event.get("competitions", []))
                    for competition in event.get("competitions", []):
                        teams_inserted += len(competition.get("competitors", []))
                        venues_inserted += 1 if competition.get("venue") else 0
                        broadcasts_inserted += len(competition.get("broadcasts", []))
                        odds_inserted += len(competition.get("odds", []))
            else:
                events_inserted, competitions_inserted, teams_inserted, venues_inserted, broadcasts_inserted, odds_inserted = self._ingest_scoreboard_data(data)

            status = ResultStatus.SUCCESS
            logger.info(
                "ESPN scoreboard ingest complete: %d events, %d competitions, %d teams, %d venues, %d broadcasts, %d odds from %s",
                events_inserted,
                competitions_inserted,
                teams_inserted,
                venues_inserted,
                broadcasts_inserted,
                odds_inserted,
                path,
            )

        except Exception as exc:
            logger.exception("ESPN scoreboard ingest failed: %s", exc)
            status = ResultStatus.FAILED
            error = str(exc)

        return IngestResult(
            source=SourceType.ESPN,
            status=status,
            rows_inserted=events_inserted + competitions_inserted + teams_inserted + venues_inserted + broadcasts_inserted + odds_inserted,
            rows_skipped=0,
            start_time=start,
            end_time=datetime.utcnow(),
            error=error,
        )

    # ------------------------------------------------------------------
    # Private helpers – DB writes
    # ------------------------------------------------------------------

    def _ingest_scoreboard_data(self, data: dict) -> tuple[int, int, int, int, int, int]:
        """Ingest scoreboard data into raw tables.

        Args:
            data: Parsed ESPN scoreboard JSON.

        Returns:
            Tuple of (events_inserted, competitions_inserted, teams_inserted, venues_inserted, broadcasts_inserted, odds_inserted).
        """
        events_inserted = 0
        competitions_inserted = 0
        teams_inserted = 0
        venues_inserted = 0
        broadcasts_inserted = 0
        odds_inserted = 0

        with self.db_connection.connect() as conn:
            # Process each league (typically just MLB)
            for league in data.get("leagues", []):
                # Process each event in the league
                for event in league.get("events", []):
                    # Ingest event
                    event_params = self._map_event_row(event, league)
                    conn.execute(text("""
                        INSERT INTO raw.espn_events (
                            id, uid, date, name, short_name, season_year, season_type,
                            season_slug, week, season_display_name, source_url, loaded_at
                        ) VALUES (
                            :id, :uid, :date, :name, :short_name, :season_year, :season_type,
                            :season_slug, :week, :season_display_name, :source_url, now()
                        )
                        ON CONFLICT (id) DO UPDATE SET
                            uid = EXCLUDED.uid,
                            date = EXCLUDED.date,
                            name = EXCLUDED.name,
                            short_name = EXCLUDED.short_name,
                            season_year = EXCLUDED.season_year,
                            season_type = EXCLUDED.season_type,
                            season_slug = EXCLUDED.season_slug,
                            week = EXCLUDED.week,
                            season_display_name = EXCLUDED.season_display_name,
                            source_url = EXCLUDED.source_url,
                            loaded_at = now()
                    """), event_params)
                    events_inserted += 1

                    # Process each competition in the event (typically 1 per event)
                    for competition in event.get("competitions", []):
                        # Ingest competition
                        competition_params = self._map_competition_row(competition, event["id"])
                        conn.execute(text("""
                            INSERT INTO raw.espn_competitions (
                                id, uid, event_id, date, attendance, venue_id, source_url, loaded_at
                            ) VALUES (
                                :id, :uid, :event_id, :date, :attendance, :venue_id, :source_url, now()
                            )
                            ON CONFLICT (id) DO UPDATE SET
                                uid = EXCLUDED.uid,
                                event_id = EXCLUDED.event_id,
                                date = EXCLUDED.date,
                                attendance = EXCLUDED.attendance,
                                venue_id = EXCLUDED.venue_id,
                                source_url = EXCLUDED.source_url,
                                loaded_at = now()
                        """), competition_params)
                        competitions_inserted += 1

                        # Ingest venue (if present)
                        venue = competition.get("venue")
                        if venue:
                            venue_params = self._map_venue_row(venue)
                            conn.execute(text("""
                                INSERT INTO raw.espn_venues (
                                    id, full_name, source_url, loaded_at
                                ) VALUES (
                                    :id, :full_name, :source_url, now()
                                )
                                ON CONFLICT (id) DO UPDATE SET
                                    full_name = EXCLUDED.full_name,
                                    source_url = EXCLUDED.source_url,
                                    loaded_at = now()
                            """), venue_params)
                            venues_inserted += 1

                        # Ingest teams/competitors
                        for competitor in competition.get("competitors", []):
                            team_params = self._map_team_row(competitor, competition["id"])
                            conn.execute(text("""
                                INSERT INTO raw.espn_teams (
                                    id, competition_id, uid, home_away, winner, score, team_id, team_uid,
                                    team_slug, team_location, team_name, team_abbreviation,
                                    team_display_name, team_short_display_name, source_url, loaded_at
                                ) VALUES (
                                    :id, :competition_id, :uid, :home_away, :winner, :score, :team_id, :team_uid,
                                    :team_slug, :team_location, :team_name, :team_abbreviation,
                                    :team_display_name, :team_short_display_name, :source_url, now()
                                )
                                ON CONFLICT (id, competition_id) DO UPDATE SET
                                    uid = EXCLUDED.uid,
                                    home_away = EXCLUDED.home_away,
                                    winner = EXCLUDED.winner,
                                    score = EXCLUDED.score,
                                    team_id = EXCLUDED.team_id,
                                    team_uid = EXCLUDED.team_uid,
                                    team_slug = EXCLUDED.team_slug,
                                    team_location = EXCLUDED.team_location,
                                    team_name = EXCLUDED.team_name,
                                    team_abbreviation = EXCLUDED.team_abbreviation,
                                    team_display_name = EXCLUDED.team_display_name,
                                    team_short_display_name = EXCLUDED.team_short_display_name,
                                    source_url = EXCLUDED.source_url,
                                    loaded_at = now()
                            """), team_params)
                            teams_inserted += 1

                        # Ingest broadcasts
                        for broadcast in competition.get("broadcasts", []):
                            broadcast_params = self._map_broadcast_row(broadcast, competition["id"])
                            conn.execute(text("""
                                INSERT INTO raw.espn_broadcasts (
                                    id, competition_id, name, market, source_url, loaded_at
                                ) VALUES (
                                    :id, :competition_id, :name, :market, :source_url, now()
                                )
                                ON CONFLICT (id, competition_id) DO UPDATE SET
                                    name = EXCLUDED.name,
                                    market = EXCLUDED.market,
                                    source_url = EXCLUDED.source_url,
                                    loaded_at = now()
                            """), broadcast_params)
                            broadcasts_inserted += 1

                        # Ingest odds
                        for odd in competition.get("odds", []):
                            odds_params = self._map_odds_row(odd, competition["id"])
                            conn.execute(text("""
                                INSERT INTO raw.espn_odds (
                                    id, competition_id, provider_id, provider_name, details, source_url, loaded_at
                                ) VALUES (
                                    :id, :competition_id, :provider_id, :provider_name, :details, :source_url, now()
                                )
                                ON CONFLICT (id, competition_id) DO UPDATE SET
                                    provider_id = EXCLUDED.provider_id,
                                    provider_name = EXCLUDED.provider_name,
                                    details = EXCLUDED.details,
                                    source_url = EXCLUDED.source_url,
                                    loaded_at = now()
                            """), odds_params)
                            odds_inserted += 1

            conn.commit()

        return events_inserted, competitions_inserted, teams_inserted, venues_inserted, broadcasts_inserted, odds_inserted

    # ------------------------------------------------------------------
    # Internal utilities – Mapping functions
    # ------------------------------------------------------------------

    @staticmethod
    def _map_event_row(event: dict, league: dict) -> dict:
        """Map an ESPN event row to DB params."""
        def _str_or_none(val: Any) -> Optional[str]:
            return str(val).strip() if val not in (None, "", "null") else None

        def _int_or_none(val: Any) -> Optional[int]:
            try:
                return int(val) if val not in (None, "", "null") else None
            except (ValueError, TypeError):
                return None

        season = event.get("season", {})
        return {
            "id": _str_or_none(event.get("id")),
            "uid": _str_or_none(event.get("uid")),
            "date": _str_or_none(event.get("date")),
            "name": _str_or_none(event.get("name")),
            "short_name": _str_or_none(event.get("shortName")),
            "season_year": _int_or_none(season.get("year")),
            "season_type": _int_or_none(season.get("type")),
            "season_slug": _str_or_none(season.get("slug")),
            "week": _int_or_none(event.get("week")),
            "season_display_name": _str_or_none(season.get("displayName")),
            "source_url": event.get("$ref", ""),  # Use the $ref as source URL if available
        }

    @staticmethod
    def _map_competition_row(competition: dict, event_id: str) -> dict:
        """Map an ESPN competition row to DB params."""
        def _str_or_none(val: Any) -> Optional[str]:
            return str(val).strip() if val not in (None, "", "null") else None

        def _int_or_none(val: Any) -> Optional[int]:
            try:
                return int(val) if val not in (None, "", "null") else None
            except (ValueError, TypeError):
                return None

        return {
            "id": _str_or_none(competition.get("id")),
            "uid": _str_or_none(competition.get("uid")),
            "event_id": event_id,
            "date": _str_or_none(competition.get("date")),
            "attendance": _int_or_none(competition.get("attendance")),
            "venue_id": _str_or_none(competition.get("venue", {}).get("id")) if competition.get("venue") else None,
            "source_url": competition.get("$ref", ""),
        }

    @staticmethod
    def _map_venue_row(venue: dict) -> dict:
        """Map an ESPN venue row to DB params."""
        def _str_or_none(val: Any) -> Optional[str]:
            return str(val).strip() if val not in (None, "", "null") else None

        return {
            "id": _str_or_none(venue.get("id")),
            "full_name": _str_or_none(venue.get("fullName")),
            "source_url": venue.get("$ref", ""),
        }

    @staticmethod
    def _map_team_row(competitor: dict, competition_id: str) -> dict:
        """Map an ESPN team/competitor row to DB params."""
        def _str_or_none(val: Any) -> Optional[str]:
            return str(val).strip() if val not in (None, "", "null") else None

        def _int_or_none(val: Any) -> Optional[int]:
            try:
                return int(val) if val not in (None, "", "null") else None
            except (ValueError, TypeError):
                return None

        team = competitor.get("team", {})
        return {
            "id": _str_or_none(f"{competition_id}_{competitor.get('homeAway', 'unknown')}"),  # Composite key
            "competition_id": competition_id,
            "uid": _str_or_none(team.get("uid")),
            "home_away": _str_or_none(competitor.get("homeAway")),
            "winner": bool(competitor.get("winner", False)),
            "score": _int_or_none(competitor.get("score")),
            "team_id": _str_or_none(team.get("id")),
            "team_uid": _str_or_none(team.get("uid")),
            "team_slug": _str_or_none(team.get("slug")),
            "team_location": _str_or_none(team.get("location")),
            "team_name": _str_or_none(team.get("name")),
            "team_abbreviation": _str_or_none(team.get("abbreviation")),
            "team_display_name": _str_or_none(team.get("displayName")),
            "team_short_display_name": _str_or_none(team.get("shortDisplayName")),
            "source_url": team.get("$ref", ""),
        }

    @staticmethod
    def _map_broadcast_row(broadcast: dict, competition_id: str) -> dict:
        """Map an ESPN broadcast row to DB params."""
        def _str_or_none(val: Any) -> Optional[str]:
            return str(val).strip() if val not in (None, "", "null") else None

        return {
            "id": _str_or_none(f"{competition_id}_{hash(str(broadcast))}"),  # Simple unique ID
            "competition_id": competition_id,
            "name": _str_or_none(broadcast.get("name")),
            "market": _str_or_none(broadcast.get("market")),
            "source_url": broadcast.get("$ref", ""),
        }

    @staticmethod
    def _map_odds_row(odd: dict, competition_id: str) -> dict:
        """Map an ESPN odds row to DB params."""
        def _str_or_none(val: Any) -> Optional[str]:
            return str(val).strip() if val not in (None, "", "null") else None

        return {
            "id": _str_or_none(f"{competition_id}_{hash(str(odd))}"),  # Simple unique ID
            "competition_id": competition_id,
            "provider_id": _str_or_none(odd.get("provider", {}).get("id")),
            "provider_name": _str_or_none(odd.get("provider", {}).get("name")),
            "details": _str_or_none(odd.get("details")),
            "source_url": odd.get("$ref", ""),
        }