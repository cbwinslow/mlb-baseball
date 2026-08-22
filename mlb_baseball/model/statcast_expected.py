"""Statcast Quality of Contact & Expected Metrics (STA-03).

Computes point-in-time entering HardHit%, Barrel%, xwOBA, xBA, and xSLG for starting
pitchers, bullpens, and offenses.
Every value is computed strictly from games preceding the target game, with
doubleheader chronological tie-breaking.
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
    """Compute and update Statcast quality of contact & expected metrics in gold.game_feature.

    Returns the number of rows updated in gold.game_feature.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.retrosheet_event')")
        (event_exists,) = fetch_one(cur)
        cur.execute("SELECT to_regclass('raw.retrosheet_gameinfo')")
        (gameinfo_exists,) = fetch_one(cur)
        if not event_exists or not gameinfo_exists:
            logger.warning(
                "raw.retrosheet_event missing; skipping Statcast expected metrics enrichment"
            )
            return 0

        sql = read_sql("statcast_expected_retrosheet_update.sql")
        cur.execute(sql)
        rowcount = cur.rowcount

    conn.commit()
    logger.info("Updated %d rows with Statcast expected metrics", rowcount)
    return rowcount


def health_check() -> list[Check]:
    """Validate Statcast quality of contact and expected metrics health in gold.game_feature."""
    with get_connection() as conn, conn.cursor() as cur:
        conn.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
        cur.execute(read_sql("statcast_expected_health_check.sql"))
        row = cur.fetchone()
        if not row:
            return [
                Check(
                    name="model.statcast_expected",
                    ok=False,
                    detail="No rows returned by statcast_expected_health_check.sql",
                )
            ]

        (
            total_rows,
            home_starter_hard_hit_rows,
            away_starter_hard_hit_rows,
            home_starter_barrel_rows,
            away_starter_barrel_rows,
            home_starter_xwoba_rows,
            away_starter_xwoba_rows,
            home_starter_xba_rows,
            away_starter_xba_rows,
            home_starter_xslg_rows,
            away_starter_xslg_rows,
            home_bullpen_hard_hit_rows,
            away_bullpen_hard_hit_rows,
            home_bullpen_barrel_rows,
            away_bullpen_barrel_rows,
            home_bullpen_xwoba_rows,
            away_bullpen_xwoba_rows,
            home_bullpen_xba_rows,
            away_bullpen_xba_rows,
            home_bullpen_xslg_rows,
            away_bullpen_xslg_rows,
            home_offense_hard_hit_rows,
            away_offense_hard_hit_rows,
            home_offense_barrel_rows,
            away_offense_barrel_rows,
            home_offense_xwoba_rows,
            away_offense_xwoba_rows,
            home_offense_xba_rows,
            away_offense_xba_rows,
            home_offense_xslg_rows,
            away_offense_xslg_rows,
            starter_oob_cnt,
            bullpen_oob_cnt,
            offense_oob_cnt,
        ) = row

        checks = []
        oob_total = (starter_oob_cnt or 0) + (bullpen_oob_cnt or 0) + (offense_oob_cnt or 0)
        if oob_total > 0:
            checks.append(
                Check(
                    name="model.statcast_expected.domain",
                    ok=False,
                    detail=(
                        f"{oob_total} Statcast expected metric values were "
                        "outside valid domain bounds"
                    ),
                )
            )
        else:
            checks.append(
                Check(
                    name="model.statcast_expected.domain",
                    ok=True,
                    detail="All Statcast expected metric values within domain bounds",
                )
            )

        checks.append(
            Check(
                name="model.statcast_expected.coverage",
                ok=True,
                detail=(
                    f"Coverage: starter_xwoba home={home_starter_xwoba_rows} "
                    f"away={away_starter_xwoba_rows}, bullpen_xwoba home={home_bullpen_xwoba_rows} "
                    f"away={away_bullpen_xwoba_rows}, offense_xwoba home={home_offense_xwoba_rows} "
                    f"away={away_offense_xwoba_rows} (total={total_rows})"
                ),
            )
        )
        return checks
