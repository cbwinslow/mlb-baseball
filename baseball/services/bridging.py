"""
================================================================================
Bridging Services
Date: 2026-05-09 (updated 2026-05-11)
Script: bridging.py
Version: 2.0.0

Link entities across data sources (player IDs, team IDs, etc.).
Provides PlayerBridge and TeamBridge for cross-source ID resolution.

Inputs:  Database connection (SQLAlchemy Engine)
Outputs: ID mappings queried/written from/to baseball.player / baseball.team
================================================================================
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import text
from sqlalchemy.engine import Engine

from baseball.core.logging import get_logger

logger = get_logger(__name__)


class PlayerBridge:
    """Bridge player identities across data sources (MLBAM, Retrosheet, Statcast, etc.)."""

    def __init__(self, db_connection: Optional[Engine] = None) -> None:
        """Initialize player bridge.

        Args:
            db_connection: SQLAlchemy Engine for DB queries.
        """
        self.db = db_connection

    # ------------------------------------------------------------------
    # Lookups
    # ------------------------------------------------------------------

    def get_player_ids(
        self,
        name: str,
    ) -> dict[str, int] | None:
        """Get all cross-source IDs for a player by name.

        Searches the baseball.player table using a case-insensitive LIKE
        match on first_name + last_name.  Returns the first match.

        Args:
            name: Player name, e.g. "Shohei Ohtani" or "Ohtani".

        Returns:
            Dict mapping source name to player ID, or None if not found.
            Keys: 'mlb', 'retrosheet', 'statcast', 'fangraphs', 'lahman'
        """
        if self.db is None:
            logger.debug("PlayerBridge.get_player_ids: no DB connection, returning None")
            return None

        parts = name.strip().split()
        if len(parts) >= 2:
            first, last = parts[0], parts[-1]
            where = "LOWER(first_name) = LOWER(:first) AND LOWER(last_name) = LOWER(:last)"
            params: dict = {"first": first, "last": last}
        else:
            where = "LOWER(last_name) = LOWER(:name) OR LOWER(first_name) = LOWER(:name)"
            params = {"name": name.strip()}

        sql = text(f"""
            SELECT
                player_mlbam_id   AS mlb,
                player_retrosheet_id AS retrosheet,
                player_mlbam_id   AS statcast,
                player_fangraphs_id  AS fangraphs,
                player_lahman_id  AS lahman
            FROM baseball.player
            WHERE {where}
            LIMIT 1
        """)

        try:
            with self.db.connect() as conn:
                row = conn.execute(sql, params).fetchone()
            if row is None:
                logger.debug("PlayerBridge: player '%s' not found", name)
                return None
            return {
                "mlb": row.mlb,
                "retrosheet": row.retrosheet,
                "statcast": row.statcast,
                "fangraphs": row.fangraphs,
                "lahman": row.lahman,
            }
        except Exception as exc:
            logger.exception("PlayerBridge.get_player_ids failed: %s", exc)
            return None

    def get_player_by_mlb_id(
        self,
        mlb_id: int,
    ) -> dict | None:
        """Fetch full player record by MLBAM ID.

        Returns:
            Dict with player fields, or None if not found.
        """
        if self.db is None:
            return None

        sql = text("""
            SELECT
                player_mlbam_id, player_retrosheet_id, player_fangraphs_id,
                player_lahman_id, first_name, last_name, bats, throws,
                birth_date, debut_date, position_primary
            FROM baseball.player
            WHERE player_mlbam_id = :mlb_id
            LIMIT 1
        """)

        try:
            with self.db.connect() as conn:
                row = conn.execute(sql, {"mlb_id": mlb_id}).fetchone()
            return dict(row._mapping) if row else None
        except Exception as exc:
            logger.exception("PlayerBridge.get_player_by_mlb_id failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def add_player_mapping(
        self,
        mlb_id: Optional[int] = None,
        retrosheet_id: Optional[str] = None,
        statcast_id: Optional[int] = None,
        fangraphs_id: Optional[int] = None,
        name: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        bats: Optional[str] = None,
        throws: Optional[str] = None,
        position: Optional[str] = None,
    ) -> bool:
        """Insert or update a player ID mapping in baseball.player.

        Uses ON CONFLICT (player_mlbam_id) DO UPDATE so re-running is safe.

        Args:
            mlb_id: MLB Stats API (MLBAM) player ID (primary key).
            retrosheet_id: Retrosheet player ID string.
            statcast_id: Statcast MLBAM ID (usually same as mlb_id).
            fangraphs_id: FanGraphs player ID.
            name: Full name (split into first/last if first_name not given).
            first_name: First name.
            last_name: Last name.
            bats: Batting hand ('L', 'R', 'S').
            throws: Throwing hand ('L', 'R').
            position: Primary position string.

        Returns:
            True if successful, False on error.
        """
        if self.db is None:
            logger.warning("PlayerBridge.add_player_mapping: no DB connection")
            return False

        # Split name if needed
        if name and not first_name:
            parts = name.strip().split(maxsplit=1)
            first_name = parts[0] if parts else ""
            last_name = parts[1] if len(parts) > 1 else ""

        sql = text("""
            INSERT INTO baseball.player (
                player_mlbam_id, player_retrosheet_id, player_fangraphs_id,
                player_lahman_id,
                first_name, last_name, bats, throws, position_primary
            ) VALUES (
                :mlb_id, :retrosheet_id, :fangraphs_id,
                NULL,
                :first_name, :last_name, :bats, :throws, :position
            )
            ON CONFLICT (player_mlbam_id) DO UPDATE SET
                player_retrosheet_id = COALESCE(EXCLUDED.player_retrosheet_id, baseball.player.player_retrosheet_id),
                player_fangraphs_id  = COALESCE(EXCLUDED.player_fangraphs_id,  baseball.player.player_fangraphs_id),
                first_name           = COALESCE(EXCLUDED.first_name,           baseball.player.first_name),
                last_name            = COALESCE(EXCLUDED.last_name,            baseball.player.last_name),
                bats                 = COALESCE(EXCLUDED.bats,                 baseball.player.bats),
                throws               = COALESCE(EXCLUDED.throws,               baseball.player.throws),
                position_primary     = COALESCE(EXCLUDED.position_primary,     baseball.player.position_primary),
                updated_at           = now()
        """)

        try:
            with self.db.connect() as conn:
                conn.execute(sql, {
                    "mlb_id": mlb_id,
                    "retrosheet_id": retrosheet_id,
                    "fangraphs_id": fangraphs_id,
                    "first_name": first_name or "",
                    "last_name": last_name or "",
                    "bats": bats,
                    "throws": throws,
                    "position": position,
                })
                conn.commit()
            logger.info(
                "PlayerBridge: upserted player mlb_id=%s name='%s %s'",
                mlb_id, first_name, last_name,
            )
            return True
        except Exception as exc:
            logger.exception("PlayerBridge.add_player_mapping failed: %s", exc)
            return False


class TeamBridge:
    """Bridge team identities across data sources."""

    # Fallback static lookup for offline / no-DB usage
    TEAM_CODES: dict[str, dict[str, int | str]] = {
        "NYY": {"mlb": 147, "retrosheet": "NYA", "espn": 10},
        "BOS": {"mlb": 111, "retrosheet": "BOS", "espn": 2},
        "LAD": {"mlb": 119, "retrosheet": "LAN", "espn": 19},
        "SFG": {"mlb": 137, "retrosheet": "SFN", "espn": 26},
        "CHC": {"mlb": 112, "retrosheet": "CHN", "espn": 16},
        "HOU": {"mlb": 117, "retrosheet": "HOU", "espn": 18},
        "ATL": {"mlb": 144, "retrosheet": "ATL", "espn": 15},
        "NYM": {"mlb": 121, "retrosheet": "NYN", "espn": 21},
        "PHI": {"mlb": 143, "retrosheet": "PHI", "espn": 22},
        "STL": {"mlb": 138, "retrosheet": "SLN", "espn": 24},
        # ... abbreviated for brevity; full table populated via migrations
    }

    def __init__(self, db_connection: Optional[Engine] = None) -> None:
        """Initialize team bridge.

        Args:
            db_connection: SQLAlchemy Engine for DB queries.
        """
        self.db = db_connection

    def get_team_ids(
        self,
        code: str,
    ) -> dict[str, int] | None:
        """Get cross-source IDs for a team by abbreviation or Retrosheet code.

        Queries baseball.team first; falls back to the static TEAM_CODES dict.

        Args:
            code: Team abbreviation (e.g. 'NYY', 'BOS') or Retrosheet code ('NYA').

        Returns:
            Dict with keys 'mlb', 'retrosheet', 'espn', or None if unknown.
        """
        # Try DB first
        if self.db is not None:
            result = self._query_team(code)
            if result:
                return result

        # Fallback to static map
        upper = code.upper()
        if upper in self.TEAM_CODES:
            entry = self.TEAM_CODES[upper]
            return {
                "mlb": entry.get("mlb"),
                "retrosheet": entry.get("retrosheet"),
                "espn": entry.get("espn"),
            }
        logger.debug("TeamBridge: team code '%s' not found", code)
        return None

    def get_mlb_id(
        self,
        code: str,
    ) -> Optional[int]:
        """Convenience: return just the MLBAM team ID for a code."""
        ids = self.get_team_ids(code)
        return ids["mlb"] if ids else None

    # ------------------------------------------------------------------
    # Private DB helpers
    # ------------------------------------------------------------------

    def _query_team(
        self,
        code: str,
    ) -> dict | None:
        """Query baseball.team for a team by team_abbr or team_retrosheet_id."""
        sql = text("""
            SELECT
                team_mlbam_id   AS mlb,
                team_retrosheet_id AS retrosheet,
                team_espn_id    AS espn,
                team_abbr,
                team_name
            FROM baseball.team
            WHERE UPPER(team_abbr) = UPPER(:code)
               OR UPPER(team_retrosheet_id) = UPPER(:code)
            LIMIT 1
        """)
        try:
            with self.db.connect() as conn:
                row = conn.execute(sql, {"code": code}).fetchone()
            if row is None:
                return None
            return {
                "mlb": row.mlb,
                "retrosheet": row.retrosheet,
                "espn": row.espn,
            }
        except Exception as exc:
            logger.exception("TeamBridge._query_team failed: %s", exc)
            return None
