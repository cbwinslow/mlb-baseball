"""Catcher Framing and Called Strike Above Expected (CSAE%) (CAT-02, ADR-045).

Computes prior-season team framing value via Statcast (raw.statcast_framing)
and point-in-time in-season starting catcher CSAE% and framing runs from Retrosheet events.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import psycopg

from mlb_baseball.db import fetch_one, get_connection
from mlb_baseball.health import Check
from mlb_baseball.model.war import _BREF_TO_RETRO
from mlb_baseball.sql import read_sql

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


def compute(conn: psycopg.Connection) -> int:
    """Compute prior team framing and in-season catcher framing metrics in gold.game_feature."""
    rowcount = 0
    with conn.cursor() as cur:
        # 1. Prior-season Statcast team framing
        cur.execute("SELECT to_regclass('raw.statcast_framing')")
        (statcast_exists,) = fetch_one(cur)
        if statcast_exists:
            values_clause = ", ".join(
                f"('{bref}', '{retro}')" for bref, retro in _BREF_TO_RETRO.items()
            )
            cur.execute(read_sql("team_framing_update.sql").format(values_clause=values_clause))
            rowcount += cur.rowcount

        # 2. In-season point-in-time starting catcher CSAE% & framing runs
        cur.execute("SELECT to_regclass('raw.retrosheet_event')")
        (event_exists,) = fetch_one(cur)
        cur.execute("SELECT to_regclass('raw.retrosheet_gameinfo')")
        (gameinfo_exists,) = fetch_one(cur)
        if event_exists and gameinfo_exists:
            cur.execute(read_sql("catcher_framing_csae_update.sql"))
            rowcount += cur.rowcount

    conn.commit()
    logger.info("Updated %d rows with catcher framing metrics", rowcount)
    return rowcount


def health_check() -> list[Check]:
    """Validate catcher framing and CSAE% metric health in gold.game_feature."""
    with get_connection() as conn, conn.cursor() as cur:
        conn.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
        cur.execute(read_sql("catcher_framing_csae_health_check.sql"))
        row = cur.fetchone()
        if not row:
            return [
                Check(
                    name="model.catcher_framing",
                    ok=False,
                    detail="No rows returned by catcher_framing_csae_health_check.sql",
                )
            ]

        (
            total_rows,
            home_csae_rows,
            away_csae_rows,
            home_framing_rows,
            away_framing_rows,
            framing_oob_cnt,
        ) = row

        checks = []
        if (framing_oob_cnt or 0) > 0:
            checks.append(
                Check(
                    name="model.catcher_framing.domain",
                    ok=False,
                    detail=(
                        f"{framing_oob_cnt} catcher framing values were outside valid domain bounds"
                    ),
                )
            )
        else:
            checks.append(
                Check(
                    name="model.catcher_framing.domain",
                    ok=True,
                    detail="All catcher framing metric values within domain bounds",
                )
            )

        checks.append(
            Check(
                name="model.catcher_framing.coverage",
                ok=True,
                detail=(
                    f"Coverage: csae home={home_csae_rows} away={away_csae_rows}, "
                    f"framing_runs home={home_framing_rows} away={away_framing_rows} "
                    f"(total={total_rows})"
                ),
            )
        )
        return checks
