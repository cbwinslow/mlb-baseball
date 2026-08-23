"""Pitcher Strike Zone Command and Statcast Attack Zones (COM-01).

Computes rolling Heart%, Shadow%, Chase%, Fastball Velocity, and Velocity Delta
for starting pitchers and bullpens strictly prior to target games.
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
    """Compute pitcher command and attack zone metrics in gold.game_feature."""
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.statcast_pitch')")
        (pitch_exists,) = fetch_one(cur)
        if not pitch_exists:
            return 0

        cur.execute(read_sql("pitcher_command_update.sql"))
        rowcount = cur.rowcount

    conn.commit()
    logger.info("Updated %d rows with pitcher command metrics", rowcount)
    return rowcount


def health_check() -> list[Check]:
    """Validate pitcher command and attack zone metric health in gold.game_feature."""
    with get_connection() as conn, conn.cursor() as cur:
        conn.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
        cur.execute(read_sql("pitcher_command_health_check.sql"))
        row = cur.fetchone()
        if not row:
            return [
                Check(
                    name="model.pitcher_command",
                    ok=False,
                    detail="No rows returned by pitcher_command_health_check.sql",
                )
            ]

        (
            total_rows,
            home_starter_heart_rows,
            away_starter_heart_rows,
            home_starter_velo_rows,
            away_starter_velo_rows,
            home_bp_heart_rows,
            away_bp_heart_rows,
            command_oob_cnt,
        ) = row

        checks = []
        if (command_oob_cnt or 0) > 0:
            checks.append(
                Check(
                    name="model.pitcher_command.domain",
                    ok=False,
                    detail=(
                        f"{command_oob_cnt} command metric values were outside valid domain bounds"
                    ),
                )
            )
        else:
            checks.append(
                Check(
                    name="model.pitcher_command.domain",
                    ok=True,
                    detail="All pitcher command metric values within domain bounds",
                )
            )

        checks.append(
            Check(
                name="model.pitcher_command.coverage",
                ok=True,
                detail=(
                    f"Coverage: starter heart home={home_starter_heart_rows} "
                    f"away={away_starter_heart_rows}, starter velo home={home_starter_velo_rows} "
                    f"away={away_starter_velo_rows}, bullpen heart home={home_bp_heart_rows} "
                    f"away={away_bp_heart_rows} (total={total_rows})"
                ),
            )
        )
        return checks
