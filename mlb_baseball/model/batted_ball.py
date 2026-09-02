"""Batted-ball profile rates and quality of contact (BAT-01, OFF-10, ADR-090,
docs/archive/FEATURE_ADMISSION_QUEUE.md). Point-in-time entering GB%, FB%, LD%, and
HR/FB% for starting pitchers, bullpens, and offensive lineups.

Every value is computed strictly from games preceding the target game, with
doubleheader chronological tie-breaking.
"""

from __future__ import annotations

import psycopg

from mlb_baseball.db import fetch_one, get_connection
from mlb_baseball.health import Check
from mlb_baseball.sql import read_sql

MIN_STARTER_BBE = 30
MIN_STARTER_FB = 10

MIN_BULLPEN_BBE = 40
MIN_BULLPEN_FB = 15

MIN_BATTING_BBE = 50
MIN_BATTING_FB = 20


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
            "  AND column_name = 'battedball_cd'"
        )
        if not cur.fetchone():
            return 0
        cur.execute(
            read_sql("team_batted_ball_retrosheet_update.sql"),
            {
                "min_starter_bbe": MIN_STARTER_BBE,
                "min_starter_fb": MIN_STARTER_FB,
                "min_bullpen_bbe": MIN_BULLPEN_BBE,
                "min_bullpen_fb": MIN_BULLPEN_FB,
                "min_batting_bbe": MIN_BATTING_BBE,
                "min_batting_fb": MIN_BATTING_FB,
            },
        )
        return cur.rowcount


def health_check() -> list[Check]:
    with get_connection() as conn, conn.cursor() as cur:
        conn.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
        cur.execute(read_sql("team_batted_ball_health_check.sql"))
        (
            total_rows,
            pop_starter_gb,
            pop_starter_fb,
            pop_starter_ld,
            pop_starter_hr_per_fb,
            pop_bullpen_gb,
            pop_batting_gb,
            out_of_bounds,
        ) = fetch_one(cur)

    checks = []
    if out_of_bounds:
        checks.append(
            Check(
                "batted-ball rates in [0, 1]",
                False,
                f"{out_of_bounds} rows outside [0.0, 1.0]",
            )
        )
    else:
        checks.append(
            Check(
                "batted-ball rates in [0, 1]",
                True,
                "all computed rates within [0.0, 1.0]",
            )
        )
    return checks
