"""Pitch Movement, Vertical Separation & Batter Attack Zone Discipline (SHP-01).

Computes rolling Fastball IVB, Curve Drop, Vertical Separation, Spin RPM,
and Lineup Attack Zone Swing/Chase rates strictly prior to target games.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import psycopg

from mlb_baseball.db import fetch_one, get_connection
from mlb_baseball.health import Check
from mlb_baseball.sql import read_sql

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


def compute(conn: psycopg.Connection) -> int:
    """Compute pitch movement and batter attack zone discipline in gold.game_feature."""
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.statcast_pitch')")
        (pitch_exists,) = fetch_one(cur)
        if not pitch_exists:
            return 0

        cur.execute(read_sql("pitch_movement_update.sql"))
        rowcount = cur.rowcount

    conn.commit()
    logger.info("Updated %d rows with pitch movement metrics", rowcount)
    return rowcount


def health_check() -> list[Check]:
    """Validate pitch movement and batter discipline health in gold.game_feature."""
    with get_connection() as conn, conn.cursor() as cur:
        conn.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
        cur.execute(read_sql("pitch_movement_health_check.sql"))
        row = cur.fetchone()
        if not row:
            return [
                Check(
                    name="model.pitch_movement",
                    ok=False,
                    detail="No rows returned by pitch_movement_health_check.sql",
                )
            ]

        (
            total_rows,
            home_starter_ivb_rows,
            away_starter_ivb_rows,
            home_starter_sep_rows,
            away_starter_sep_rows,
            home_bat_chase_rows,
            away_bat_chase_rows,
            movement_oob_cnt,
        ) = row

        checks = []
        if (movement_oob_cnt or 0) > 0:
            checks.append(
                Check(
                    name="model.pitch_movement.domain",
                    ok=False,
                    detail=(
                        f"{movement_oob_cnt} pitch movement metric values "
                        "outside valid physical bounds"
                    ),
                )
            )
        else:
            checks.append(
                Check(
                    name="model.pitch_movement.domain",
                    ok=True,
                    detail="All pitch movement metric values within valid physical bounds",
                )
            )

        checks.append(
            Check(
                name="model.pitch_movement.coverage",
                ok=True,
                detail=(
                    f"Coverage: starter IVB home={home_starter_ivb_rows} "
                    f"away={away_starter_ivb_rows}, starter vert separation "
                    f"home={home_starter_sep_rows} away={away_starter_sep_rows}, "
                    f"batting chase home={home_bat_chase_rows} away={away_bat_chase_rows} "
                    f"(total={total_rows})"
                ),
            )
        )
        return checks
