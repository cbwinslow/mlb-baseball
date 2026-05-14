"""
================================================================================
FanGraphs Ingestor
Date: 2026-05-13
Script: ingestor.py
Version: 1.0.0

Load FanGraphs downloaded CSV files into the database.
Supports dry-run mode when no DB connection is provided.

Inputs:  CSV files produced by FanGraphsDownloader
Outputs: Rows upserted into raw.fg_batting, raw.fg_pitching, raw.fg_fielding
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


class FanGraphsIngestor:
    """Ingest FanGraphs data into the database."""

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
                "FanGraphsIngestor initialised without a DB connection – "
                "running in dry-run mode (no data will be written)"
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def ingest_batting_stats(
        self,
        path: Path,
        season: int,
    ) -> IngestResult:
        """Ingest a batting statistics CSV file produced by FanGraphsDownloader.

        Args:
            path: Path to the batting statistics CSV file.
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
                raise FileNotFoundError(f"Batting stats file not found: {path}")

            with open(path, newline="", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                rows = list(reader)

            if self._dry_run:
                logger.info(
                    "[dry-run] Would ingest %d batting rows for season %s from %s",
                    len(rows),
                    season,
                    path,
                )
                rows_inserted = len(rows)
            else:
                rows_inserted, rows_skipped = self._upsert_batting_rows(rows, season)

            status = ResultStatus.SUCCESS
            logger.info(
                "FanGraphs batting ingest complete: %d inserted, %d skipped (season=%s)",
                rows_inserted,
                rows_skipped,
                season,
            )

        except Exception as exc:
            logger.exception("FanGraphs batting ingest failed: %s", exc)
            status = ResultStatus.FAILED
            error = str(exc)

        return IngestResult(
            source=SourceType.FANGRAPHS,
            status=status,
            rows_inserted=rows_inserted,
            rows_skipped=rows_skipped,
            start_time=start,
            end_time=datetime.utcnow(),
            error=error,
        )

    def ingest_pitching_stats(
        self,
        path: Path,
        season: int,
    ) -> IngestResult:
        """Ingest a pitching statistics CSV file produced by FanGraphsDownloader.

        Args:
            path: Path to the pitching statistics CSV file.
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
                raise FileNotFoundError(f"Pitching stats file not found: {path}")

            with open(path, newline="", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                rows = list(reader)

            if self._dry_run:
                logger.info(
                    "[dry-run] Would ingest %d pitching rows for season %s from %s",
                    len(rows),
                    season,
                    path,
                )
                rows_inserted = len(rows)
            else:
                rows_inserted, rows_skipped = self._upsert_pitching_rows(rows, season)

            status = ResultStatus.SUCCESS
            logger.info(
                "FanGraphs pitching ingest complete: %d inserted, %d skipped (season=%s)",
                rows_inserted,
                rows_skipped,
                season,
            )

        except Exception as exc:
            logger.exception("FanGraphs pitching ingest failed: %s", exc)
            status = ResultStatus.FAILED
            error = str(exc)

        return IngestResult(
            source=SourceType.FANGRAPHS,
            status=status,
            rows_inserted=rows_inserted,
            rows_skipped=rows_skipped,
            start_time=start,
            end_time=datetime.utcnow(),
            error=error,
        )

    def ingest_fielding_stats(
        self,
        path: Path,
        season: int,
    ) -> IngestResult:
        """Ingest a fielding statistics CSV file produced by FanGraphsDownloader.

        Args:
            path: Path to the fielding statistics CSV file.
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
                raise FileNotFoundError(f"Fielding stats file not found: {path}")

            with open(path, newline="", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                rows = list(reader)

            if self._dry_run:
                logger.info(
                    "[dry-run] Would ingest %d fielding rows for season %s from %s",
                    len(rows),
                    season,
                    path,
                )
                rows_inserted = len(rows)
            else:
                rows_inserted, rows_skipped = self._upsert_fielding_rows(rows, season)

            status = ResultStatus.SUCCESS
            logger.info(
                "FanGraphs fielding ingest complete: %d inserted, %d skipped (season=%s)",
                rows_inserted,
                rows_skipped,
                season,
            )

        except Exception as exc:
            logger.exception("FanGraphs fielding ingest failed: %s", exc)
            status = ResultStatus.FAILED
            error = str(exc)

        return IngestResult(
            source=SourceType.FANGRAPHS,
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

    def _upsert_batting_rows(
        self, rows: list[dict], season: int
    ) -> tuple[int, int]:
        """Insert or update batting rows in raw.fg_batting.

        Uses PostgreSQL INSERT ... ON CONFLICT (playerid, season, team) DO UPDATE
        so that re-running an ingest for the same season is always idempotent.

        Args:
            rows: List of dicts from csv.DictReader.
            season: Season year to stamp on every row.

        Returns:
            Tuple of (rows_inserted, rows_skipped).  Because ON CONFLICT DO
            UPDATE always writes, we count all rows as inserted and skip=0.
        """
        upsert_sql = text("""
            INSERT INTO raw.fg_batting (
                playerid, season, name, team, age, g, ab, pa, h, "1b", "2b", "3b",
                hr, r, rbi, bb, ibb, so, hbp, sf, sh, gdp, sb, cs, avg, obp, slg,
                ops, bb_pct, k_pct, bb_k, woba, wrc_plus, wrc, wraa, off, def_val,
                "war", gb_pct, fb_pct, ld_pct, iffb_pct, hr_fb, gb_fb, pull_pct,
                cent_pct, oppo_pct, soft_pct, med_pct, hard_pct, ev, la, barrels,
                barrel_pct, maxev, hard_hit_pct, xba, xslg, xwoba, xwrc_plus, xera,
                o_swing_pct, z_swing_pct, swing_pct, o_contact_pct, z_contact_pct,
                contact_pct, zone_pct, f_strike_pct, swstr_pct, wpa, neg_wpa,
                pos_wpa, re24, rew, pli, phli, ph_r, wpa_li, clutch, source_url,
                loaded_at
            ) VALUES (
                :playerid, :season, :name, :team, :age, :g, :ab, :pa, :h, :1b, :2b,
                :3b, :hr, :r, :rbi, :bb, :ibb, :so, :hbp, :sf, :sh, :gdp, :sb,
                :cs, :avg, :obp, :slg, :ops, :bb_pct, :k_pct, :bb_k, :woba,
                :wrc_plus, :wrc, :wraa, :off, :def_val, :war, :gb_pct, :fb_pct,
                :ld_pct, :iffb_pct, :hr_fb, :gb_fb, :pull_pct, :cent_pct,
                :oppo_pct, :soft_pct, :med_pct, :hard_pct, :ev, :la, :barrels,
                :barrel_pct, :maxev, :hard_hit_pct, :xba, :xslg, :xwoba,
                :xwrc_plus, :xera, :o_swing_pct, :z_swing_pct, :swing_pct,
                :o_contact_pct, :z_contact_pct, :contact_pct, :zone_pct,
                :f_strike_pct, :swstr_pct, :wpa, :neg_wpa, :pos_wpa, :re24,
                :rew, :pli, :phli, :ph_r, :wpa_li, :clutch, :source_url, now()
            )
            ON CONFLICT (playerid, season, team) DO UPDATE SET
                name = EXCLUDED.name,
                age = EXCLUDED.age,
                g = EXCLUDED.g,
                ab = EXCLUDED.ab,
                pa = EXCLUDED.pa,
                h = EXCLUDED.h,
                "1b" = EXCLUDED."1b",
                "2b" = EXCLUDED."2b",
                "3b" = EXCLUDED."3b",
                hr = EXCLUDED.hr,
                r = EXCLUDED.r,
                rbi = EXCLUDED.rbi,
                bb = EXCLUDED.bb,
                ibb = EXCLUDED.ibb,
                so = EXCLUDED.so,
                hbp = EXCLUDED.hbp,
                sf = EXCLUDED.sf,
                sh = EXCLUDED.sh,
                gdp = EXCLUDED.gdp,
                sb = EXCLUDED.sb,
                cs = EXCLUDED.cs,
                avg = EXCLUDED.avg,
                obp = EXCLUDED.obp,
                slg = EXCLUDED.slg,
                ops = EXCLUDED.ops,
                bb_pct = EXCLUDED.bb_pct,
                k_pct = EXCLUDED.k_pct,
                bb_k = EXCLUDED.bb_k,
                woba = EXCLUDED.woba,
                wrc_plus = EXCLUDED.wrc_plus,
                wrc = EXCLUDED.wrc,
                wraa = EXCLUDED.wraa,
                off = EXCLUDED.off,
                def_val = EXCLUDED.def_val,
                war = EXCLUDED.war,
                gb_pct = EXCLUDED.gb_pct,
                fb_pct = EXCLUDED.fb_pct,
                ld_pct = EXCLUDED.ld_pct,
                iffb_pct = EXCLUDED.iffb_pct,
                hr_fb = EXCLUDED.hr_fb,
                gb_fb = EXCLUDED.gb_fb,
                pull_pct = EXCLUDED.pull_pct,
                cent_pct = EXCLUDED.cent_pct,
                oppo_pct = EXCLUDED.oppo_pct,
                soft_pct = EXCLUDED.soft_pct,
                med_pct = EXCLUDED.med_pct,
                hard_pct = EXCLUDED.hard_pct,
                ev = EXCLUDED.ev,
                la = EXCLUDED.la,
                barrels = EXCLUDED.barrels,
                barrel_pct = EXCLUDED.barrel_pct,
                maxev = EXCLUDED.maxev,
                hard_hit_pct = EXCLUDED.hard_hit_pct,
                xba = EXCLUDED.xba,
                xslg = EXCLUDED.xslg,
                xwoba = EXCLUDED.xwoba,
                xwrc_plus = EXCLUDED.xwrc_plus,
                xera = EXCLUDED.xera,
                o_swing_pct = EXCLUDED.o_swing_pct,
                z_swing_pct = EXCLUDED.z_swing_pct,
                swing_pct = EXCLUDED.swing_pct,
                o_contact_pct = EXCLUDED.o_contact_pct,
                z_contact_pct = EXCLUDED.z_contact_pct,
                contact_pct = EXCLUDED.contact_pct,
                zone_pct = EXCLUDED.zone_pct,
                f_strike_pct = EXCLUDED.f_strike_pct,
                swstr_pct = EXCLUDED.swstr_pct,
                wpa = EXCLUDED.wpa,
                neg_wpa = EXCLUDED.neg_wpa,
                pos_wpa = EXCLUDED.pos_wpa,
                re24 = EXCLUDED.re24,
                rew = EXCLUDED.rew,
                pli = EXCLUDED.pli,
                phli = EXCLUDED.phli,
                ph_r = EXCLUDED.ph_r,
                wpa_li = EXCLUDED.wpa_li,
                clutch = EXCLUDED.clutch,
                source_url = EXCLUDED.source_url,
                loaded_at = now()
        """)

        params = [self._map_batting_row(row, season) for row in rows]

        with self.db_connection.connect() as conn:
            conn.execute(upsert_sql, params)
            conn.commit()

        logger.debug("_upsert_batting_rows: wrote %d rows for season %s", len(rows), season)
        return len(rows), 0

    def _upsert_pitching_rows(
        self, rows: list[dict], season: int
    ) -> tuple[int, int]:
        """Insert or update pitching rows in raw.fg_pitching.

        Uses PostgreSQL INSERT ... ON CONFLICT (playerid, season, team) DO UPDATE
        so that re-running an ingest for the same season is always idempotent.

        Args:
            rows: List of dicts from csv.DictReader.
            season: Season year to stamp on every row.

        Returns:
            Tuple of (rows_inserted, rows_skipped).  Because ON CONFLICT DO
            UPDATE always writes, we count all rows as inserted and skip=0.
        """
        upsert_sql = text("""
            INSERT INTO raw.fg_pitching (
                playerid, season, name, team, age, w, l, sv, g, gs, cg, sho, hld,
                bs, ip, tbf, h, r, er, hr, bb, ibb, hbp, wp, bk, so, era, ra9,
                fip, xfip, siera, k_9, bb_9, k_bb, h_9, hr_9, avg, whip, babip,
                lob_pct, gb_pct, fb_pct, ld_pct, hr_fb, k_pct, bb_pct, ev, la,
                barrels, barrel_pct, maxev, hard_hit_pct, xba, xslg, xwoba, xera,
                o_swing_pct, z_swing_pct, swing_pct, o_contact_pct, z_contact_pct,
                contact_pct, zone_pct, f_strike_pct, swstr_pct, war, source_url,
                loaded_at
            ) VALUES (
                :playerid, :season, :name, :team, :age, :w, :l, :sv, :g, :gs,
                :cg, :sho, :hld, :bs, :ip, :tbf, :h, :r, :er, :hr, :bb, :ibb,
                :hbp, :wp, :bk, :so, :era, :ra9, :fip, :xfip, :siera, :k_9,
                :bb_9, :k_bb, :h_9, :hr_9, :avg, :whip, :babip, :lob_pct,
                :gb_pct, :fb_pct, :ld_pct, :hr_fb, :k_pct, :bb_pct, :ev, :la,
                :barrels, :barrel_pct, :maxev, :hard_hit_pct, :xba, :xslg,
                :xwoba, :xera, :o_swing_pct, :z_swing_pct, :swing_pct,
                :o_contact_pct, :z_contact_pct, :contact_pct, :zone_pct,
                :f_strike_pct, :swstr_pct, :war, :source_url, now()
            )
            ON CONFLICT (playerid, season, team) DO UPDATE SET
                name = EXCLUDED.name,
                age = EXCLUDED.age,
                w = EXCLUDED.w,
                l = EXCLUDED.l,
                sv = EXCLUDED.sv,
                g = EXCLUDED.g,
                gs = EXCLUDED.gs,
                cg = EXCLUDED.cg,
                sho = EXCLUDED.sho,
                hld = EXCLUDED.hld,
                bs = EXCLUDED.bs,
                ip = EXCLUDED.ip,
                tbf = EXCLUDED.tbf,
                h = EXCLUDED.h,
                r = EXCLUDED.r,
                er = EXCLUDED.er,
                hr = EXCLUDED.hr,
                bb = EXCLUDED.bb,
                ibb = EXCLUDED.ibb,
                hbp = EXCLUDED.hbp,
                wp = EXCLUDED.wp,
                bk = EXCLUDED.bk,
                so = EXCLUDED.so,
                era = EXCLUDED.era,
                ra9 = EXCLUDED.ra9,
                fip = EXCLUDED.fip,
                xfip = EXCLUDED.xfip,
                siera = EXCLUDED.siera,
                k_9 = EXCLUDED.k_9,
                bb_9 = EXCLUDED.bb_9,
                k_bb = EXCLUDED.k_bb,
                h_9 = EXCLUDED.h_9,
                hr_9 = EXCLUDED.hr_9,
                avg = EXCLUDED.avg,
                whip = EXCLUDED.whip,
                babip = EXCLUDED.babip,
                lob_pct = EXCLUDED.lob_pct,
                gb_pct = EXCLUDED.gb_pct,
                fb_pct = EXCLUDED.fb_pct,
                ld_pct = EXCLUDED.ld_pct,
                hr_fb = EXCLUDED.hr_fb,
                k_pct = EXCLUDED.k_pct,
                bb_pct = EXCLUDED.bb_pct,
                ev = EXCLUDED.ev,
                la = EXCLUDED.la,
                barrels = EXCLUDED.barrels,
                barrel_pct = EXCLUDED.barrel_pct,
                maxev = EXCLUDED.maxev,
                hard_hit_pct = EXCLUDED.hard_hit_pct,
                xba = EXCLUDED.xba,
                xslg = EXCLUDED.xslg,
                xwoba = EXCLUDED.xwoba,
                xera = EXCLUDED.xera,
                o_swing_pct = EXCLUDED.o_swing_pct,
                z_swing_pct = EXCLUDED.z_swing_pct,
                swing_pct = EXCLUDED.swing_pct,
                o_contact_pct = EXCLUDED.o_contact_pct,
                z_contact_pct = EXCLUDED.z_contact_pct,
                contact_pct = EXCLUDED.contact_pct,
                zone_pct = EXCLUDED.zone_pct,
                f_strike_pct = EXCLUDED.f_strike_pct,
                swstr_pct = EXCLUDED.swstr_pct,
                war = EXCLUDED.war,
                source_url = EXCLUDED.source_url,
                loaded_at = now()
        """)

        params = [self._map_pitching_row(row, season) for row in rows]

        with self.db_connection.connect() as conn:
            conn.execute(upsert_sql, params)
            conn.commit()

        logger.debug("_upsert_pitching_rows: wrote %d rows for season %s", len(rows), season)
        return len(rows), 0

    def _upsert_fielding_rows(
        self, rows: list[dict], season: int
    ) -> tuple[int, int]:
        """Insert or update fielding rows in raw.fg_fielding.

        Uses PostgreSQL INSERT ... ON CONFLICT (playerid, pos, season, team) DO UPDATE
        so that re-running an ingest for the same season is always idempotent.

        Args:
            rows: List of dicts from csv.DictReader.
            season: Season year to stamp on every row.

        Returns:
            Tuple of (rows_inserted, rows_skipped).  Because ON CONFLICT DO
            UPDATE always writes, we count all rows as inserted and skip=0.
        """
        upsert_sql = text("""
            INSERT INTO raw.fg_fielding (
                playerid, season, name, team, pos, age, g, gs, inn, po, a, e,
                dp, fpct, drs, biz, plays, rszr, rng, rng_r, err_r, arm_r,
                dp_r, sbr, ubr, frm_runs, "def", source_url, loaded_at
            ) VALUES (
                :playerid, :season, :name, :team, :pos, :age, :g, :gs, :inn,
                :po, :a, :e, :dp, :fpct, :drs, :biz, :plays, :rszr, :rng,
                :rng_r, :err_r, :arm_r, :dp_r, :sbr, :ubr, :frm_runs, :def,
                :source_url, now()
            )
            ON CONFLICT (playerid, pos, season, team) DO UPDATE SET
                name = EXCLUDED.name,
                team = EXCLUDED.team,
                age = EXCLUDED.age,
                g = EXCLUDED.g,
                gs = EXCLUDED.gs,
                inn = EXCLUDED.inn,
                po = EXCLUDED.po,
                a = EXCLUDED.a,
                e = EXCLUDED.e,
                dp = EXCLUDED.dp,
                fpct = EXCLUDED.fpct,
                drs = EXCLUDED.drs,
                biz = EXCLUDED.biz,
                plays = EXCLUDED.plays,
                rszr = EXCLUDED.rszr,
                rng = EXCLUDED.rng,
                rng_r = EXCLUDED.rng_r,
                err_r = EXCLUDED.err_r,
                arm_r = EXCLUDED.arm_r,
                dp_r = EXCLUDED.dp_r,
                sbr = EXCLUDED.sbr,
                ubr = EXCLUDED.ubr,
                frm_runs = EXCLUDED.frm_runs,
                def = EXCLUDED.def,
                source_url = EXCLUDED.source_url,
                loaded_at = now()
        """)

        params = [self._map_fielding_row(row, season) for row in rows]

        with self.db_connection.connect() as conn:
            conn.execute(upsert_sql, params)
            conn.commit()

        logger.debug("_upsert_fielding_rows: wrote %d rows for season %s", len(rows), season)
        return len(rows), 0

    # ------------------------------------------------------------------
    # Internal utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _map_batting_row(row: dict, season: int) -> dict:
        """Normalise a raw CSV row dict into a params dict for the upsert."""
        def _int_or_none(val: str) -> Optional[int]:
            try:
                return int(val) if val not in ("", None) else None
            except (ValueError, TypeError):
                return None

        def _float_or_none(val: str) -> Optional[float]:
            try:
                return float(val) if val not in ("", None) else None
            except (ValueError, TypeError):
                return None

        return {
            "playerid": row.get("PlayerID", ""),
            "season": season,
            "name": row.get("Name", ""),
            "team": row.get("Team", ""),
            "age": _int_or_none(row.get("Age")),
            "g": _int_or_none(row.get("G")),
            "ab": _int_or_none(row.get("AB")),
            "pa": _int_or_none(row.get("PA")),
            "h": _int_or_none(row.get("H")),
            "1b": _int_or_none(row.get("1B")),
            "2b": _int_or_none(row.get("2B")),
            "3b": _int_or_none(row.get("3B")),
            "hr": _int_or_none(row.get("HR")),
            "r": _int_or_none(row.get("R")),
            "rbi": _int_or_none(row.get("RBI")),
            "bb": _int_or_none(row.get("BB")),
            "ibb": _int_or_none(row.get("IBB")),
            "so": _int_or_none(row.get("SO")),
            "hbp": _int_or_none(row.get("HBP")),
            "sf": _int_or_none(row.get("SF")),
            "sh": _int_or_none(row.get("SH")),
            "gdp": _int_or_none(row.get("GDP")),
            "sb": _int_or_none(row.get("SB")),
            "cs": _int_or_none(row.get("CS")),
            "avg": _float_or_none(row.get("AVG")),
            "obp": _float_or_none(row.get("OBP")),
            "slg": _float_or_none(row.get("SLG")),
            "ops": _float_or_none(row.get("OPS")),
            "bb_pct": _float_or_none(row.get("BB%")),
            "k_pct": _float_or_none(row.get("K%")),
            "bb_k": _float_or_none(row.get("BB/K")),
            "woba": _float_or_none(row.get("wOBA")),
            "wrc_plus": _float_or_none(row.get("wRC+")),
            "wrc": _float_or_none(row.get("wRC")),
            "wraa": _float_or_none(row.get("wRAA")),
            "off": _float_or_none(row.get("Off")),
            "def_val": _float_or_none(row.get("Def")),
            "war": _float_or_none(row.get("WAR")),
            "gb_pct": _float_or_none(row.get("GB%")),
            "fb_pct": _float_or_none(row.get("FB%")),
            "ld_pct": _float_or_none(row.get("LD%")),
            "iffb_pct": _float_or_none(row.get("IF%")),
            "hr_fb": _float_or_none(row.get("HR/FB")),
            "gb_fb": _float_or_none(row.get("GB/FB")),
            "pull_pct": _float_or_none(row.get("Pull%")),
            "cent_pct": _float_or_none(row.get("Cent%")),
            "oppo_pct": _float_or_none(row.get("Oppo%")),
            "soft_pct": _float_or_none(row.get("Soft%")),
            "med_pct": _float_or_none(row.get("Med%")),
            "hard_pct": _float_or_none(row.get("Hard%")),
            "ev": _float_or_none(row.get("EV")),
            "la": _float_or_none(row.get("LaunchAngle")),
            "barrels": _int_or_none(row.get("Barrels")),
            "barrel_pct": _float_or_none(row.get("Barrel%")),
            "maxev": _float_or_none(row.get("MaxEV")),
            "hard_hit_pct": _float_or_none(row.get("HardHit%")),
            "xba": _float_or_none(row.get("xBA")),
            "xslg": _float_or_none(row.get("xSLG")),
            "xwoba": _float_or_none(row.get("xwOBA")),
            "xwrc_plus": _float_or_none(row.get("xwRC+")),
            "xera": _float_or_none(row.get("xERA")),
            "o_swing_pct": _float_or_none(row.get("O-Swing%")),
            "z_swing_pct": _float_or_none(row.get("Z-Swing%")),
            "swing_pct": _float_or_none(row.get("Swing%")),
            "o_contact_pct": _float_or_none(row.get("O-Contact%")),
            "z_contact_pct": _float_or_none(row.get("Z-Contact%")),
            "contact_pct": _float_or_none(row.get("Contact%")),
            "zone_pct": _float_or_none(row.get("Zone%")),
            "f_strike_pct": _float_or_none(row.get("F-Strike%")),
            "swstr_pct": _float_or_none(row.get("SwStr%")),
            "wpa": _float_or_none(row.get("WPA")),
            "neg_wpa": _float_or_none(row.get("-WPA")),
            "pos_wpa": _float_or_none(row.get("+WPA")),
            "re24": _float_or_none(row.get("RE24")),
            "rew": _float_or_none(row.get("REW")),
            "pli": _float_or_none(row.get("PLI")),
            "phli": _float_or_none(row.get("PHLI")),
            "ph_r": _float_or_none(row.get("PH")),
            "wpa_li": _float_or_none(row.get("WPA/LI")),
            "clutch": _float_or_none(row.get("Clutch")),
            "source_url": row.get("source_url", ""),
        }

    @staticmethod
    def _map_pitching_row(row: dict, season: int) -> dict:
        """Normalise a raw CSV row dict into a params dict for the upsert."""
        def _int_or_none(val: str) -> Optional[int]:
            try:
                return int(val) if val not in ("", None) else None
            except (ValueError, TypeError):
                return None

        def _float_or_none(val: str) -> Optional[float]:
            try:
                return float(val) if val not in ("", None) else None
            except (ValueError, TypeError):
                return None

        return {
            "playerid": row.get("PlayerID", ""),
            "season": season,
            "name": row.get("Name", ""),
            "team": row.get("Team", ""),
            "age": _int_or_none(row.get("Age")),
            "w": _int_or_none(row.get("W")),
            "l": _int_or_none(row.get("L")),
            "sv": _int_or_none(row.get("SV")),
            "g": _int_or_none(row.get("G")),
            "gs": _int_or_none(row.get("GS")),
            "cg": _int_or_none(row.get("CG")),
            "sho": _int_or_none(row.get("SHO")),
            "hld": _int_or_none(row.get("HLD")),
            "bs": _int_or_none(row.get("BS")),
            "ip": _float_or_none(row.get("IP")),
            "tbf": _int_or_none(row.get("TBF")),
            "h": _int_or_none(row.get("H")),
            "r": _int_or_none(row.get("R")),
            "er": _int_or_none(row.get("ER")),
            "hr": _int_or_none(row.get("HR")),
            "bb": _int_or_none(row.get("BB")),
            "ibb": _int_or_none(row.get("IBB")),
            "hbp": _int_or_none(row.get("HBP")),
            "wp": _int_or_none(row.get("WP")),
            "bk": _int_or_none(row.get("BK")),
            "so": _int_or_none(row.get("SO")),
            "era": _float_or_none(row.get("ERA")),
            "ra9": _float_or_none(row.get("RA9")),
            "fip": _float_or_none(row.get("FIP")),
            "xfip": _float_or_none(row.get("xFIP")),
            "siera": _float_or_none(row.get("SIERA")),
            "k_9": _float_or_none(row.get("K/9")),
            "bb_9": _float_or_none(row.get("BB/9")),
            "k_bb": _float_or_none(row.get("K/BB")),
            "h_9": _float_or_none(row.get("H/9")),
            "hr_9": _float_or_none(row.get("HR/9")),
            "avg": _float_or_none(row.get("AVG")),
            "whip": _float_or_none(row.get("WHIP")),
            "babip": _float_or_none(row.get("BABIP")),
            "lob_pct": _float_or_none(row.get("LOB%")),
            "gb_pct": _float_or_none(row.get("GB%")),
            "fb_pct": _float_or_none(row.get("FB%")),
            "ld_pct": _float_or_none(row.get("LD%")),
            "hr_fb": _float_or_none(row.get("HR/FB")),
            "k_pct": _float_or_none(row.get("K%")),
            "bb_pct": _float_or_none(row.get("BB%")),
            "ev": _float_or_none(row.get("EV")),
            "la": _float_or_none(row.get("LaunchAngle")),
            "barrels": _int_or_none(row.get("Barrels")),
            "barrel_pct": _float_or_none(row.get("Barrel%")),
            "maxev": _float_or_none(row.get("MaxEV")),
            "hard_hit_pct": _float_or_none(row.get("HardHit%")),
            "xba": _float_or_none(row.get("xBA")),
            "xslg": _float_or_none(row.get("xSLG")),
            "xwoba": _float_or_none(row.get("xwOBA")),
            "xera": _float_or_none(row.get("xERA")),
            "o_swing_pct": _float_or_none(row.get("O-Swing%")),
            "z_swing_pct": _float_or_none(row.get("Z-Swing%")),
            "swing_pct": _float_or_none(row.get("Swing%")),
            "o_contact_pct": _float_or_none(row.get("O-Contact%")),
            "z_contact_pct": _float_or_none(row.get("Z-Contact%")),
            "contact_pct": _float_or_none(row.get("Contact%")),
            "zone_pct": _float_or_none(row.get("Zone%")),
            "f_strike_pct": _float_or_none(row.get("F-Strike%")),
            "swstr_pct": _float_or_none(row.get("SwStr%")),
            "war": _float_or_none(row.get("WAR")),
            "source_url": row.get("source_url", ""),
        }

    @staticmethod
    def _map_fielding_row(row: dict, season: int) -> dict:
        """Normalise a raw CSV row dict into a params dict for the upsert."""
        def _int_or_none(val: str) -> Optional[int]:
            try:
                return int(val) if val not in ("", None) else None
            except (ValueError, TypeError):
                return None

        def _float_or_none(val: str) -> Optional[float]:
            try:
                return float(val) if val not in ("", None) else None
            except (ValueError, TypeError):
                return None

        return {
            "playerid": row.get("PlayerID", ""),
            "season": season,
            "name": row.get("Name", ""),
            "team": row.get("Team", ""),
            "pos": row.get("Pos", ""),
            "age": _int_or_none(row.get("Age")),
            "g": _int_or_none(row.get("G")),
            "gs": _int_or_none(row.get("GS")),
            "inn": _float_or_none(row.get("Inn")),
            "po": _int_or_none(row.get("PO")),
            "a": _int_or_none(row.get("A")),
            "e": _int_or_none(row.get("E")),
            "dp": _int_or_none(row.get("DP")),
            "fpct": _float_or_none(row.get("FPct")),
            "drs": _float_or_none(row.get("DRS")),
            "biz": _int_or_none(row.get("BIZ")),
            "plays": _int_or_none(row.get("Plays")),
            "rszr": _float_or_none(row.get("RSZ")),
            "rng": _float_or_none(row.get("Rng")),
            "rng_r": _float_or_none(row.get("Rng/9")),
            "err_r": _float_or_none(row.get("Err/9")),
            "arm_r": _float_or_none(row.get("Arm/9")),
            "dp_r": _float_or_none(row.get("DP/9")),
            "sbr": _float_or_none(row.get("SB/9")),
            "ubr": _float_or_none(row.get("UBR")),
            "frm_runs": _float_or_none(row.get("FRM")),
            "def": _float_or_none(row.get("Def")),
            "source_url": row.get("source_url", ""),
        }