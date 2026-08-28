"""Comprehensive Baserunning: wSB, XBT%, UBR, wGDP, and Total BsR (RUN-01).

Computes point-in-time entering baserunning run values and advance rates
strictly from games preceding the target game.
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
    """Compute comprehensive BsR metrics in gold.game_feature."""
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.retrosheet_event')")
        (event_exists,) = fetch_one(cur)
        cur.execute("SELECT to_regclass('raw.retrosheet_gameinfo')")
        (gameinfo_exists,) = fetch_one(cur)
        if not event_exists or not gameinfo_exists:
            logger.warning("Retrosheet tables missing; skipping BsR enrichment")
            return 0

        cur.execute(read_sql("team_bsr_comprehensive_retrosheet_update.sql"))
        rowcount = cur.rowcount

    conn.commit()
    logger.info("Updated %d rows with comprehensive BsR metrics", rowcount)
    return rowcount


def health_check() -> list[Check]:
    """Validate comprehensive baserunning metric health in gold.game_feature."""
    with get_connection() as conn, conn.cursor() as cur:
        conn.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
        cur.execute(read_sql("team_bsr_comprehensive_health_check.sql"))
        row = cur.fetchone()
        if not row:
            return [
                Check(
                    name="model.bsr_comprehensive",
                    ok=False,
                    detail="No rows returned by team_bsr_comprehensive_health_check.sql",
                )
            ]

        (
            total_rows,
            home_wsb_rows,
            away_wsb_rows,
            home_xbt_rows,
            away_xbt_rows,
            home_ubr_rows,
            away_ubr_rows,
            home_wgdp_rows,
            away_wgdp_rows,
            home_bsr_rows,
            away_bsr_rows,
            bsr_oob_cnt,
        ) = row

        checks = []
        if (bsr_oob_cnt or 0) > 0:
            checks.append(
                Check(
                    name="model.bsr_comprehensive.domain",
                    ok=False,
                    detail=f"{bsr_oob_cnt} baserunning values were outside valid domain bounds",
                )
            )
        else:
            checks.append(
                Check(
                    name="model.bsr_comprehensive.domain",
                    ok=True,
                    detail="All baserunning metric values within domain bounds",
                )
            )

        checks.append(
            Check(
                name="model.bsr_comprehensive.coverage",
                ok=True,
                detail=(
                    f"Coverage: wsb home={home_wsb_rows} away={away_wsb_rows}, "
                    f"xbt home={home_xbt_rows} away={away_xbt_rows}, "
                    f"bsr_total home={home_bsr_rows} away={away_bsr_rows} (total={total_rows})"
                ),
            )
        )
        return checks
