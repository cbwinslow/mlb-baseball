"""Run Expectancy (RE24) and Leverage Index (LI) metrics (ADR-090, Package 3).

Point-in-time entering average Leverage Index (LI) and RE24 for starting
pitchers, bullpens, and offensive lineups.

Every value is computed strictly from games preceding the target game, with
doubleheader chronological tie-breaking.
"""

from __future__ import annotations

import psycopg

from mlb_baseball.db import fetch_one, get_connection
from mlb_baseball.health import Check
from mlb_baseball.sql import read_sql

MIN_STARTER_PA = 30
MIN_BULLPEN_PA = 40
MIN_BATTING_PA = 50


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
            "  AND column_name = 'event_runs_ct'"
        )
        if not cur.fetchone():
            return 0

        # Build empirical 24-state matrix if table is empty
        cur.execute("SELECT count(*) FROM gold.run_expectancy_24")
        (re24_count,) = fetch_one(cur)
        if re24_count == 0:
            cur.execute(read_sql("run_expectancy_matrix_build.sql"))

        cur.execute(
            read_sql("team_leverage_re24_update.sql"),
            {
                "min_starter_pa": MIN_STARTER_PA,
                "min_bullpen_pa": MIN_BULLPEN_PA,
                "min_batting_pa": MIN_BATTING_PA,
            },
        )
        return cur.rowcount


def health_check() -> list[Check]:
    with get_connection() as conn, conn.cursor() as cur:
        conn.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
        cur.execute(read_sql("team_leverage_re24_health_check.sql"))
        (
            invalid_h_sp_li,
            invalid_a_sp_li,
            invalid_h_bp_li,
            invalid_a_bp_li,
        ) = fetch_one(cur)

    checks = []
    total_invalid = invalid_h_sp_li + invalid_a_sp_li + invalid_h_bp_li + invalid_a_bp_li
    if total_invalid > 0:
        checks.append(
            Check(
                "leverage index in [0, inf)",
                False,
                f"{total_invalid} rows with negative leverage index",
            )
        )
    else:
        checks.append(
            Check(
                "leverage index in [0, inf)",
                True,
                "all computed leverage indices non-negative",
            )
        )
    return checks
