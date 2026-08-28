"""Platoon Splits & Handedness Matchups feature family (PLT-01, ADR-101).

Computes pitcher throwing hand, team offense vs LHP/RHP wOBA, and net platoon advantage deltas.
"""

from __future__ import annotations

import logging

import psycopg

from mlb_baseball.db import fetch_one, get_connection
from mlb_baseball.health import Check
from mlb_baseball.sql import read_sql

logger = logging.getLogger(__name__)

_PLATOON_UPDATE_SQL = read_sql("platoon_splits_update.sql")
_PLATOON_HEALTH_CHECK_SQL = read_sql("platoon_splits_health_check.sql")


def compute(conn: psycopg.Connection) -> int:
    """Enrich gold.game_feature with platoon splits and handedness matchup differences."""
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.statcast_pitch')")
        (table_exists,) = fetch_one(cur)
        if not table_exists:
            return 0

        cur.execute(_PLATOON_UPDATE_SQL)
        rowcount = cur.rowcount

    conn.commit()
    logger.info("Updated %d rows with platoon splits and handedness metrics", rowcount)
    return rowcount


def health_check() -> list[Check]:
    """Run health assertions on platoon splits features."""
    checks: list[Check] = []
    with get_connection() as conn, conn.cursor() as cur:
        conn.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
        cur.execute(_PLATOON_HEALTH_CHECK_SQL)
        row = cur.fetchone()
        if not row:
            return [
                Check(
                    name="model.platoon",
                    ok=False,
                    detail="No rows returned by platoon_splits_health_check.sql",
                )
            ]

        total, bad_h_throws, bad_a_throws, oob_h_diff, oob_a_diff = row

        checks.append(
            Check(
                name="platoon_starter_throws_validity",
                ok=(bad_h_throws == 0 and bad_a_throws == 0),
                detail=f"Invalid throws: home={bad_h_throws}, away={bad_a_throws} (total={total})",
            )
        )

        checks.append(
            Check(
                name="platoon_matchup_woba_diff_bounds",
                ok=(oob_h_diff == 0 and oob_a_diff == 0),
                detail=f"Out of bounds diffs [-0.30, 0.30]: home={oob_h_diff}, away={oob_a_diff}",
            )
        )

    return checks
