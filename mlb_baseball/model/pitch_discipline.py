"""Plate discipline, pitch counts, and pitch sequence rates (PIT-07, ADR-089,
docs/archive/FEATURE_ADMISSION_QUEUE.md). Point-in-time entering CSW%, Whiff%, and
First-Pitch Strike% for starting pitchers and bullpens.

Every value is computed strictly from games preceding the target game, with
doubleheader chronological tie-breaking.
"""

from __future__ import annotations

import psycopg

from mlb_baseball.db import fetch_one, get_connection
from mlb_baseball.health import Check
from mlb_baseball.sql import read_sql

MIN_STARTER_PITCHES = 20
MIN_STARTER_SWINGS = 10
MIN_STARTER_PA = 5

MIN_BULLPEN_PITCHES = 30
MIN_BULLPEN_SWINGS = 15


def compute(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.retrosheet_event')")
        (event_exists,) = fetch_one(cur)
        cur.execute("SELECT to_regclass('raw.retrosheet_gameinfo')")
        (gameinfo_exists,) = fetch_one(cur)
        if not event_exists or not gameinfo_exists:
            return 0
        cur.execute(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = 'raw' AND table_name = 'retrosheet_event' "
            "  AND column_name = 'pitch_seq_tx'"
        )
        if not cur.fetchone():
            return 0
        cur.execute(
            read_sql("team_pitch_discipline_retrosheet_update.sql"),
            {
                "min_starter_pitches": MIN_STARTER_PITCHES,
                "min_starter_swings": MIN_STARTER_SWINGS,
                "min_starter_pa": MIN_STARTER_PA,
                "min_bullpen_pitches": MIN_BULLPEN_PITCHES,
                "min_bullpen_swings": MIN_BULLPEN_SWINGS,
            },
        )
        return cur.rowcount


def health_check() -> list[Check]:
    with get_connection() as conn, conn.cursor() as cur:
        conn.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
        cur.execute(read_sql("team_pitch_discipline_health_check.sql"))
        (
            bad_h_csw,
            bad_a_csw,
            bad_h_whiff,
            bad_a_whiff,
            bad_h_fstrike,
            bad_a_fstrike,
            bad_hb_csw,
            bad_ab_csw,
            bad_hb_whiff,
            bad_ab_whiff,
        ) = fetch_one(cur)

    def _check(name: str, bad: int) -> Check:
        if bad:
            return Check(name, False, f"{bad} rows outside [0.0, 1.0]")
        return Check(name, True, "all computed values within [0.0, 1.0]")

    return [
        _check("starter csw% in [0, 1]", bad_h_csw + bad_a_csw),
        _check("starter whiff% in [0, 1]", bad_h_whiff + bad_a_whiff),
        _check("starter first-pitch strike% in [0, 1]", bad_h_fstrike + bad_a_fstrike),
        _check("bullpen csw% in [0, 1]", bad_hb_csw + bad_ab_csw),
        _check("bullpen whiff% in [0, 1]", bad_hb_whiff + bad_ab_whiff),
    ]
