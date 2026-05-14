"""
================================================================================
Lahman Ingestor
Date: 2026-05-13
Script: ingestor.py
Version: 1.0.0

Load Lahman downloaded CSV files into the database.
Supports dry-run mode when no DB connection is provided.

Inputs:  CSV files produced by LahmanDownloader
Outputs: Rows upserted into raw.lahman_* tables
================================================================================
"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import text
from sqlalchemy.engine import Engine

from baseball.core.enums import ResultStatus, SourceType
from baseball.core.logging import get_logger
from baseball.core.results import IngestResult

logger = get_logger(__name__)


class LahmanIngestor:
    """Ingest Lahman data into the database."""

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
                "LahmanIngestor initialised without a DB connection – "
                "running in dry-run mode (no data will be written)"
            )

    # ------------------------------------------------------------------
    # Public API - Batting
    # ------------------------------------------------------------------

    def ingest_batting(
        self,
        path: Path,
    ) -> IngestResult:
        """Ingest a batting CSV file produced by LahmanDownloader.

        Args:
            path: Path to the batting CSV file.

        Returns:
            IngestResult with row counts and timing.
        """
        return self._ingest_csv(
            path,
            table="raw.lahman_batting",
            conflict_cols=["playerID", "yearID", "teamID", "stint"],
            map_func=self._map_batting_row,
        )

    # ------------------------------------------------------------------
    # Public API - Pitching
    # ------------------------------------------------------------------

    def ingest_pitching(
        self,
        path: Path,
    ) -> IngestResult:
        """Ingest a pitching CSV file produced by LahmanDownloader.

        Args:
            path: Path to the pitching CSV file.

        Returns:
            IngestResult with row counts and timing.
        """
        return self._ingest_csv(
            path,
            table="raw.lahman_pitching",
            conflict_cols=["playerID", "yearID", "teamID", "stint"],
            map_func=self._map_pitching_row,
        )

    # ------------------------------------------------------------------
    # Public API - Fielding
    # ------------------------------------------------------------------

    def ingest_fielding(
        self,
        path: Path,
    ) -> IngestResult:
        """Ingest a fielding CSV file produced by LahmanDownloader.

        Args:
            path: Path to the fielding CSV file.

        Returns:
            IngestResult with row counts and timing.
        """
        return self._ingest_csv(
            path,
            table="raw.lahman_fielding",
            conflict_cols=["playerID", "yearID", "teamID", "POS", "stint"],
            map_func=self._map_fielding_row,
        )

    # ------------------------------------------------------------------
    # Public API - People
    # ------------------------------------------------------------------

    def ingest_people(
        self,
        path: Path,
    ) -> IngestResult:
        """Ingest a people CSV file produced by LahmanDownloader.

        Args:
            path: Path to the people CSV file.

        Returns:
            IngestResult with row counts and timing.
        """
        return self._ingest_csv(
            path,
            table="raw.lahman_people",
            conflict_cols=["playerID"],
            map_func=self._map_people_row,
        )

    # ------------------------------------------------------------------
    # Public API - Teams
    # ------------------------------------------------------------------

    def ingest_teams(
        self,
        path: Path,
    ) -> IngestResult:
        """Ingest a teams CSV file produced by LahmanDownloader.

        Args:
            path: Path to the teams CSV file.

        Returns:
            IngestResult with row counts and timing.
        """
        return self._ingest_csv(
            path,
            table="raw.lahman_teams",
            conflict_cols=["teamID", "yearID", "lgID"],
            map_func=self._map_teams_row,
        )

    # ------------------------------------------------------------------
    # Public API - Appearances
    # ------------------------------------------------------------------

    def ingest_appearances(
        self,
        path: Path,
    ) -> IngestResult:
        """Ingest an appearances CSV file produced by LahmanDownloader.

        Args:
            path: Path to the appearances CSV file.

        Returns:
            IngestResult with row counts and timing.
        """
        return self._ingest_csv(
            path,
            table="raw.lahman_appearances",
            conflict_cols=["playerID", "yearID", "teamID", "lgID", "POS"],
            map_func=self._map_appearances_row,
        )

    # ------------------------------------------------------------------
    # Public API - Managers
    # ------------------------------------------------------------------

    def ingest_managers(
        self,
        path: Path,
    ) -> IngestResult:
        """Ingest a managers CSV file produced by LahmanDownloader.

        Args:
            path: Path to the managers CSV file.

        Returns:
            IngestResult with row counts and timing.
        """
        return self._ingest_csv(
            path,
            table="raw.lahman_managers",
            conflict_cols=["playerID", "yearID", "teamID", "lgID", "inseason"],
            map_func=self._map_managers_row,
        )

    # ------------------------------------------------------------------
    # Public API - Salaries
    # ------------------------------------------------------------------

    def ingest_salaries(
        self,
        path: Path,
    ) -> IngestResult:
        """Ingest a salaries CSV file produced by LahmanDownloader.

        Args:
            path: Path to the salaries CSV file.

        Returns:
            IngestResult with row counts and timing.
        """
        return self._ingest_csv(
            path,
            table="raw.lahman_salaries",
            conflict_cols=["playerID", "yearID", "teamID", "lgID"],
            map_func=self._map_salaries_row,
        )

    # ------------------------------------------------------------------
    # Public API - Awards
    # ------------------------------------------------------------------

    def ingest_awards(
        self,
        path: Path,
    ) -> IngestResult:
        """Ingest an awards CSV file produced by LahmanDownloader.

        Args:
            path: Path to the awards CSV file.

        Returns:
            IngestResult with row counts and timing.
        """
        return self._ingest_csv(
            path,
            table="raw.lahman_awards",
            conflict_cols=["playerID", "yearID", "awardID", "lgID", "tie", "notes"],
            map_func=self._map_awards_row,
        )

    # ------------------------------------------------------------------
    # Public API - Allstar
    # ------------------------------------------------------------------

    def ingest_allstar(
        self,
        path: Path,
    ) -> IngestResult:
        """Ingest an allstar CSV file produced by LahmanDownloader.

        Args:
            path: Path to the allstar CSV file.

        Returns:
            IngestResult with row counts and timing.
        """
        return self._ingest_csv(
            path,
            table="raw.lahman_allstar",
            conflict_cols=["playerID", "yearID", "gameNum", "gameID", "teamID", "lgID"],
            map_func=self._map_allstar_row,
        )

    # ------------------------------------------------------------------
    # Public API - Parks
    # ------------------------------------------------------------------

    def ingest_parks(
        self,
        path: Path,
    ) -> IngestResult:
        """Ingest a parks CSV file produced by LahmanDownloader.

        Args:
            path: Path to the parks CSV file.

        Returns:
            IngestResult with row counts and timing.
        """
        return self._ingest_csv(
            path,
            table="raw.lahman_parks",
            conflict_cols=["parkKey"],
            map_func=self._map_parks_row,
        )

    # ------------------------------------------------------------------
    # Public API - Awards Share
    # ------------------------------------------------------------------

    def ingest_awardsshare(
        self,
        path: Path,
    ) -> IngestResult:
        """Ingest an awardsshare CSV file produced by LahmanDownloader.

        Args:
            path: Path to the awardsshare CSV file.

        Returns:
            IngestResult with row counts and timing.
        """
        return self._ingest_csv(
            path,
            table="raw.lahman_awardsshare",
            conflict_cols=["awardID", "yearID", "lgID", "playerID", "ptsWon", "ptsMax", "share"],
            map_func=self._map_awardsshare_row,
        )

    # ------------------------------------------------------------------
    # Public API - Hall of Fame
    # ------------------------------------------------------------------

    def ingest_hof(
        self,
        path: Path,
    ) -> IngestResult:
        """Ingest a hof CSV file produced by LahmanDownloader.

        Args:
            path: Path to the hof CSV file.

        Returns:
            IngestResult with row counts and timing.
        """
        return self._ingest_csv(
            path,
            table="raw.lahman_hof",
            conflict_cols=["playerID", "yearID", "votedBy", "ballots", "needed", "votes", "inducted", "category"],
            map_func=self._map_hof_row,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _ingest_csv(
        self,
        path: Path,
        table: str,
        conflict_cols: list[str],
        map_func,
    ) -> IngestResult:
        """Generic CSV ingest method.

        Args:
            path: Path to the CSV file.
            table: Target table name.
            conflict_cols: Columns to use for ON CONFLICT clause.
            map_func: Function to map CSV row to DB params.

        Returns:
            IngestResult with row counts and timing.
        """
        start = datetime.utcnow()
        rows_inserted = 0
        rows_skipped = 0
        error = None

        try:
            if not path.exists():
                raise FileNotFoundError(f"File not found: {path}")

            with open(path, newline="", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                rows = list(reader)

            if self._dry_run:
                logger.info(
                    "[dry-run] Would ingest %d rows from %s",
                    len(rows),
                    path,
                )
                rows_inserted = len(rows)
            else:
                rows_inserted, rows_skipped = self._upsert_rows(
                    rows, table, conflict_cols, map_func
                )

            status = ResultStatus.SUCCESS
            logger.info(
                "Lahman ingest complete: %d inserted, %d skipped from %s",
                rows_inserted,
                rows_skipped,
                path,
            )

        except Exception as exc:
            logger.exception("Lahman ingest failed for %s: %s", path, exc)
            status = ResultStatus.FAILED
            error = str(exc)

        return IngestResult(
            source=SourceType.LAHMAN,
            status=status,
            rows_inserted=rows_inserted,
            rows_skipped=rows_skipped,
            start_time=start,
            end_time=datetime.utcnow(),
            error=error,
        )

    def _upsert_rows(
        self,
        rows: list[dict],
        table: str,
        conflict_cols: list[str],
        map_func,
    ) -> tuple[int, int]:
        """Insert or update rows in a table.

        Uses PostgreSQL INSERT ... ON CONFLICT (...) DO UPDATE.

        Args:
            rows: List of dicts from csv.DictReader.
            table: Target table name.
            conflict_cols: Columns to use for ON CONFLICT clause.
            map_func: Function to map CSV row to DB params.

        Returns:
            Tuple of (rows_inserted, rows_skipped).
        """
        # Build the column list and placeholders dynamically
        sample_row = map_func(rows[0]) if rows else {}
        columns = list(sample_row.keys())
        
        # Build the SQL
        columns_str = ", ".join(columns)
        placeholders_str = ", ".join([f":{col}" for col in columns])
        conflict_str = ", ".join(conflict_cols)
        
        # Build the UPDATE SET clause (exclude conflict columns)
        update_cols = [col for col in columns if col not in conflict_cols]
        update_str = ", ".join([f"{col} = EXCLUDED.{col}" for col in update_cols])
        
        upsert_sql = text(f"""
            INSERT INTO {table} ({columns_str})
            VALUES ({placeholders_str})
            ON CONFLICT ({conflict_str}) DO UPDATE SET
                {update_str}
        """)

        # Map all rows
        params = [map_func(row) for row in rows]

        with self.db_connection.connect() as conn:
            conn.execute(upsert_sql, params)
            conn.commit()

        logger.debug("_upsert_rows: wrote %d rows to %s", len(rows), table)
        return len(rows), 0

    # ------------------------------------------------------------------
    # Mapping functions for each table
    # ------------------------------------------------------------------

    @staticmethod
    def _map_batting_row(row: dict) -> dict:
        """Map a Batting CSV row to DB params."""
        def _int_or_none(val: str) -> Optional[int]:
            try:
                return int(val) if val not in ("", None) else None
            except (ValueError, TypeError):
                return None

        return {
            "playerID": row.get("playerID"),
            "yearID": _int_or_none(row.get("yearID")),
            "stint": _int_or_none(row.get("stint")),
            "teamID": row.get("teamID"),
            "lgID": row.get("lgID"),
            "G": _int_or_none(row.get("G")),
            "AB": _int_or_none(row.get("AB")),
            "R": _int_or_none(row.get("R")),
            "H": _int_or_none(row.get("H")),
            "2B": _int_or_none(row.get("2B")),
            "3B": _int_or_none(row.get("3B")),
            "HR": _int_or_none(row.get("HR")),
            "RBI": _int_or_none(row.get("RBI")),
            "SB": _int_or_none(row.get("SB")),
            "CS": _int_or_none(row.get("CS")),
            "BB": _int_or_none(row.get("BB")),
            "SO": _int_or_none(row.get("SO")),
            "IBB": _int_or_none(row.get("IBB")),
            "HBP": _int_or_none(row.get("HBP")),
            "SH": _int_or_none(row.get("SH")),
            "SF": _int_or_none(row.get("SF")),
            "GIDP": _int_or_none(row.get("GIDP")),
        }

    @staticmethod
    def _map_pitching_row(row: dict) -> dict:
        """Map a Pitching CSV row to DB params."""
        def _int_or_none(val: str) -> Optional[int]:
            try:
                return int(val) if val not in ("", None) else None
            except (ValueError, TypeError):
                return None

        return {
            "playerID": row.get("playerID"),
            "yearID": _int_or_none(row.get("yearID")),
            "stint": _int_or_none(row.get("stint")),
            "teamID": row.get("teamID"),
            "lgID": row.get("lgID"),
            "W": _int_or_none(row.get("W")),
            "L": _int_or_none(row.get("L")),
            "G": _int_or_none(row.get("G")),
            "GS": _int_or_none(row.get("GS")),
            "CG": _int_or_none(row.get("CG")),
            "SHO": _int_or_none(row.get("SHO")),
            "SV": _int_or_none(row.get("SV")),
            "IPouts": _int_or_none(row.get("IPouts")),
            "H": _int_or_none(row.get("H")),
            "ER": _int_or_none(row.get("ER")),
            "HR": _int_or_none(row.get("HR")),
            "BB": _int_or_none(row.get("BB")),
            "SO": _int_or_none(row.get("SO")),
            "BAOPP": _int_or_none(row.get("BAOPP")),
            "ERA": _float_or_none(row.get("ERA")),
            "IBB": _int_or_none(row.get("IBB")),
            "WP": _int_or_none(row.get("WP")),
            "HBP": _int_or_none(row.get("HBP")),
            "BK": _int_or_none(row.get("BK")),
            "BFP": _int_or_none(row.get("BFP")),
            "GF": _int_or_none(row.get("GF")),
            "R": _int_or_none(row.get("R")),
            "SH": _int_or_none(row.get("SH")),
            "SF": _int_or_none(row.get("SF")),
            "GIDP": _int_or_none(row.get("GIDP")),
        }

    @staticmethod
    def _map_fielding_row(row: dict) -> dict:
        """Map a Fielding CSV row to DB params."""
        def _int_or_none(val: str) -> Optional[int]:
            try:
                return int(val) if val not in ("", None) else None
            except (ValueError, TypeError):
                return None

        return {
            "playerID": row.get("playerID"),
            "yearID": _int_or_none(row.get("yearID")),
            "stint": _int_or_none(row.get("stint")),
            "teamID": row.get("teamID"),
            "lgID": row.get("lgID"),
            "POS": row.get("POS"),
            "G": _int_or_none(row.get("G")),
            "GS": _int_or_none(row.get("GS")),
            "InnOuts": _int_or_none(row.get("InnOuts")),
            "PO": _int_or_none(row.get("PO")),
            "A": _int_or_none(row.get("A")),
            "E": _int_or_none(row.get("E")),
            "DP": _int_or_none(row.get("DP")),
            "TP": _int_or_none(row.get("TP")),
            "PB": _int_or_none(row.get("PB")),
            "SB": _int_or_none(row.get("SB")),
            "CS": _int_or_none(row.get("CS")),
            "ZR": _int_or_none(row.get("ZR")),
        }

    @staticmethod
    def _map_people_row(row: dict) -> dict:
        """Map a People CSV row to DB params."""
        def _int_or_none(val: str) -> Optional[int]:
            try:
                return int(val) if val not in ("", None) else None
            except (ValueError, TypeError):
                return None

        return {
            "playerID": row.get("playerID"),
            "birthYear": _int_or_none(row.get("birthYear")),
            "birthMonth": _int_or_none(row.get("birthMonth")),
            "birthDay": _int_or_none(row.get("birthDay")),
            "birthCountry": row.get("birthCountry"),
            "birthState": row.get("birthState"),
            "birthCity": row.get("birthCity"),
            "deathYear": _int_or_none(row.get("deathYear")),
            "deathMonth": _int_or_none(row.get("deathMonth")),
            "deathDay": _int_or_none(row.get("deathDay")),
            "deathCountry": row.get("deathCountry"),
            "deathState": row.get("deathState"),
            "deathCity": row.get("deathCity"),
            "nameFirst": row.get("nameFirst"),
            "nameLast": row.get("nameLast"),
            "nameGiven": row.get("nameGiven"),
            "weight": _int_or_none(row.get("weight")),
            "height": _int_or_none(row.get("height")),
            "bats": row.get("bats"),
            "throws": row.get("throws"),
            "debut": row.get("debut"),
            "finalGame": row.get("finalGame"),
            "retroID": row.get("retroID"),
            "bbrefID": row.get("bbrefID"),
        }

    @staticmethod
    def _map_teams_row(row: dict) -> dict:
        """Map a Teams CSV row to DB params."""
        def _int_or_none(val: str) -> Optional[int]:
            try:
                return int(val) if val not in ("", None) else None
            except (ValueError, TypeError):
                return None

        return {
            "teamID": row.get("teamID"),
            "yearID": _int_or_none(row.get("yearID")),
            "lgID": row.get("lgID"),
            "franchID": row.get("franchID"),
            "divID": row.get("divID"),
            "Rank": _int_or_none(row.get("Rank")),
            "G": _int_or_none(row.get("G")),
            "Ghome": _int_or_none(row.get("Ghome")),
            "W": _int_or_none(row.get("W")),
            "L": _int_or_none(row.get("L")),
            "DivWin": row.get("DivWin"),
            "WCWin": row.get("WCWin"),
            "LgWin": row.get("LgWin"),
            "WSWin": row.get("WSWin"),
            "R": _int_or_none(row.get("R")),
            "AB": _int_or_none(row.get("AB")),
            "H": _int_or_none(row.get("H")),
            "2B": _int_or_none(row.get("2B")),
            "3B": _int_or_none(row.get("3B")),
            "HR": _int_or_none(row.get("HR")),
            "BB": _int_or_none(row.get("BB")),
            "SO": _int_or_none(row.get("SO")),
            "SB": _int_or_none(row.get("SB")),
            "CS": _int_or_none(row.get("CS")),
            "HBP": _int_or_none(row.get("HBP")),
            "SF": _int_or_none(row.get("SF")),
            "RA": _int_or_none(row.get("RA")),
            "ER": _int_or_none(row.get("ER")),
            "ERA": _float_or_none(row.get("ERA")),
            "CG": _int_or_none(row.get("CG")),
            "SHO": _int_or_none(row.get("SHO")),
            "SV": _int_or_none(row.get("SV")),
            "IPouts": _int_or_none(row.get("IPouts")),
            "HA": _int_or_none(row.get("HA")),
            "HRA": _int_or_none(row.get("HRA")),
            "BBA": _int_or_none(row.get("BBA")),
            "SOA": _int_or_none(row.get("SOA")),
            "E": _int_or_none(row.get("E")),
            "DP": _int_or_none(row.get("DP")),
            "FP": _float_or_none(row.get("FP")),
            "name": row.get("name"),
            "park": row.get("park"),
            "attendance": _int_or_none(row.get("attendance")),
            "BPF": _float_or_none(row.get("BPF")),
            "PPF": _float_or_none(row.get("PPF")),
            "teamIDBR": row.get("teamIDBR"),
            "teamIDlahman45": row.get("teamIDlahman45"),
            "teamIDretro": row.get("teamIDretro"),
        }

    @staticmethod
    def _map_appearances_row(row: dict) -> dict:
        """Map an Appearances CSV row to DB params."""
        def _int_or_none(val: str) -> Optional[int]:
            try:
                return int(val) if val not in ("", None) else None
            except (ValueError, TypeError):
                return None

        return {
            "playerID": row.get("playerID"),
            "yearID": _int_or_none(row.get("yearID")),
            "teamID": row.get("teamID"),
            "lgID": row.get("lgID"),
            "GS": _int_or_none(row.get("GS")),
            "G_batting": _int_or_none(row.get("G_batting")),
            "AB": _int_or_none(row.get("AB")),
            "R": _int_or_none(row.get("R")),
            "H": _int_or_none(row.get("H")),
            "2B": _int_or_none(row.get("2B")),
            "3B": _int_or_none(row.get("3B")),
            "HR": _int_or_none(row.get("HR")),
            "RBI": _int_or_none(row.get("RBI")),
            "SB": _int_or_none(row.get("SB")),
            "CS": _int_or_none(row.get("CS")),
            "BB": _int_or_none(row.get("BB")),
            "SO": _int_or_none(row.get("SO")),
            "IBB": _int_or_none(row.get("IBB")),
            "HBP": _int_or_none(row.get("HBP")),
            "SH": _int_or_none(row.get("SH")),
            "SF": _int_or_none(row.get("SF")),
            "GIDP": _int_or_none(row.get("GIDP")),
            "G_old": _int_or_none(row.get("G_old")),
            "G_p": _int_or_none(row.get("G_p")),
            "GS_p": _int_or_none(row.get("GS_p")),
            "G_c": _int_or_none(row.get("G_c")),
            "GS_c": _int_or_none(row.get("GS_c")),
            "G_1b": _int_or_none(row.get("G_1b")),
            "GS_1b": _int_or_none(row.get("GS_1b")),
            "G_2b": _int_or_none(row.get("G_2b")),
            "GS_2b": _int_or_none(row.get("GS_2b")),
            "G_3b": _int_or_none(row.get("G_3b")),
            "GS_3b": _int_or_none(row.get("GS_3b")),
            "G_ss": _int_or_none(row.get("G_ss")),
            "GS_ss": _int_or_none(row.get("GS_ss")),
            "G_lf": _int_or_none(row.get("G_lf")),
            "GS_lf": _int_or_none(row.get("GS_lf")),
            "G_cf": _int_or_none(row.get("G_cf")),
            "GS_cf": _int_or_none(row.get("GS_cf")),
            "G_rf": _int_or_none(row.get("G_rf")),
            "GS_rf": _int_or_none(row.get("GS_rf")),
            "G_of": _int_or_none(row.get("G_of")),
            "GS_of": _int_or_none(row.get("GS_of")),
            "G_dh": _int_or_none(row.get("G_dh")),
            "GS_dh": _int_or_none(row.get("GS_dh")),
            "G_ph": _int_or_none(row.get("G_ph")),
            "GS_ph": _int_or_none(row.get("GS_ph")),
            "G_pr": _int_or_none(row.get("G_pr")),
            "GS_pr": _int_or_none(row.get("GS_pr")),
        }

    @staticmethod
    def _map_managers_row(row: dict) -> dict:
        """Map a Managers CSV row to DB params."""
        def _int_or_none(val: str) -> Optional[int]:
            try:
                return int(val) if val not in ("", None) else None
            except (ValueError, TypeError):
                return None

        return {
            "playerID": row.get("playerID"),
            "yearID": _int_or_none(row.get("yearID")),
            "teamID": row.get("teamID"),
            "lgID": row.get("lgID"),
            "inseason": _int_or_none(row.get("inseason")),
            "G": _int_or_none(row.get("G")),
            "W": _int_or_none(row.get("W")),
            "L": _int_or_none(row.get("L")),
            "rank": _int_or_none(row.get("rank")),
            "yrmgr": row.get("yrmgr"),
        }

    @staticmethod
    def _map_salaries_row(row: dict) -> dict:
        """Map a Salaries CSV row to DB params."""
        def _int_or_none(val: str) -> Optional[int]:
            try:
                return int(val) if val not in ("", None) else None
            except (ValueError, TypeError):
                return None

        return {
            "yearID": _int_or_none(row.get("yearID")),
            "teamID": row.get("teamID"),
            "lgID": row.get("lgID"),
            "playerID": row.get("playerID"),
            "salary": _int_or_none(row.get("salary")),
        }

    @staticmethod
    def _map_awards_row(row: dict) -> dict:
        """Map an Awards CSV row to DB params."""
        def _int_or_none(val: str) -> Optional[int]:
            try:
                return int(val) if val not in ("", None) else None
            except (ValueError, TypeError):
                return None

        return {
            "playerID": row.get("playerID"),
            "yearID": _int_or_none(row.get("yearID")),
            "awardID": row.get("awardID"),
            "lgID": row.get("lgID"),
            "tie": _int_or_none(row.get("tie")),
            "notes": row.get("notes"),
        }

    @staticmethod
    def _map_allstar_row(row: dict) -> dict:
        """Map an Allstar CSV row to DB params."""
        def _int_or_none(val: str) -> Optional[int]:
            try:
                return int(val) if val not in ("", None) else None
            except (ValueError, TypeError):
                return None

        return {
            "playerID": row.get("playerID"),
            "yearID": _int_or_none(row.get("yearID")),
            "gameNum": _int_or_none(row.get("gameNum")),
            "gameID": row.get("gameID"),
            "teamID": row.get("teamID"),
            "lgID": row.get("lgID"),
            "GP": _int_or_none(row.get("GP")),
            "startingPos": _int_or_none(row.get("startingPos")),
        }

    @staticmethod
    def _map_parks_row(row: dict) -> dict:
        """Map a Parks CSV row to DB params."""
        def _int_or_none(val: str) -> Optional[int]:
            try:
                return int(val) if val not in ("", None) else None
            except (ValueError, TypeError):
                return None

        return {
            "parkKey": row.get("parkKey"),
            "parkName": row.get("parkName"),
            "city": row.get("city"),
            "state": row.get("state"),
            "country": row.get("country"),
        }

    @staticmethod
    def _map_awardsshare_row(row: dict) -> dict:
        """Map an AwardsShare CSV row to DB params."""
        def _int_or_none(val: str) -> Optional[int]:
            try:
                return int(val) if val not in ("", None) else None
            except (ValueError, TypeError):
                return None

        return {
            "awardID": row.get("awardID"),
            "yearID": _int_or_none(row.get("yearID")),
            "lgID": row.get("lgID"),
            "playerID": row.get("playerID"),
            "ptsWon": _int_or_none(row.get("ptsWon")),
            "ptsMax": _int_or_none(row.get("ptsMax")),
            "share": _float_or_none(row.get("share")),
        }

    @staticmethod
    def _map_hof_row(row: dict) -> dict:
        """Map a Hall of Fame CSV row to DB params."""
        def _int_or_none(val: str) -> Optional[int]:
            try:
                return int(val) if val not in ("", None) else None
            except (ValueError, TypeError):
                return None

        return {
            "playerID": row.get("playerID"),
            "yearID": _int_or_none(row.get("yearID")),
            "votedBy": row.get("votedBy"),
            "ballots": _int_or_none(row.get("ballots")),
            "needed": _int_or_none(row.get("needed")),
            "votes": _int_or_none(row.get("votes")),
            "inducted": _int_or_none(row.get("inducted")),
            "category": row.get("category"),
        }

    # Helper functions
    @staticmethod
    def _float_or_none(val: str) -> Optional[float]:
        try:
            return float(val) if val not in ("", None) else None
        except (ValueError, TypeError):
            return None