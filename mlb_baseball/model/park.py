"""Park factors and Environmental Weather Adjustments (PARK-01, WEA-01).

Computes multi-year trailing run park factors (1yr, 3yr, 5yr), component park factors
(HR, 2B, 3B, LHB/RHB HR), air density index, and effective center-field wind vectors.
Point-in-time correct by construction: trailing windows strictly precede the target season.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import psycopg

from mlb_baseball.db import get_connection
from mlb_baseball.health import Check
from mlb_baseball.sql import read_sql

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

TRAILING_SEASONS = 3


def compute(conn: psycopg.Connection) -> int:
    """Compute multi-year component park factors and weather features in gold.game_feature."""
    with conn.cursor() as cur:
        # Base park factor calculation
        cur.execute(
            read_sql("park_factors_weather_update.sql"),
        )
        rowcount = cur.rowcount

    conn.commit()
    logger.info("Updated %d rows with park factors and weather features", rowcount)
    return rowcount


def health_check() -> list[Check]:
    """Validate Multi-Year Park Factors and Environmental Weather health in gold.game_feature."""
    with get_connection() as conn, conn.cursor() as cur:
        conn.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
        cur.execute(read_sql("park_factors_weather_health_check.sql"))
        row = cur.fetchone()
        if not row:
            return [
                Check(
                    name="model.park_factors_weather",
                    ok=False,
                    detail="No rows returned by park_factors_weather_health_check.sql",
                )
            ]

        (
            total_rows,
            park_factor_1yr_rows,
            park_factor_3yr_rows,
            park_factor_5yr_rows,
            park_hr_factor_rows,
            park_2b_factor_rows,
            park_3b_factor_rows,
            park_lhb_hr_factor_rows,
            park_rhb_hr_factor_rows,
            air_density_rows,
            effective_wind_rows,
            wind_direction_rows,
            park_factor_oob_cnt,
            weather_oob_cnt,
        ) = row

        checks = []
        oob_total = (park_factor_oob_cnt or 0) + (weather_oob_cnt or 0)
        if oob_total > 0:
            checks.append(
                Check(
                    name="model.park_factors_weather.domain",
                    ok=False,
                    detail=(
                        f"{oob_total} park factor or weather values "
                        "were outside valid domain bounds"
                    ),
                )
            )
        else:
            checks.append(
                Check(
                    name="model.park_factors_weather.domain",
                    ok=True,
                    detail="All park factor and environmental weather values within domain bounds",
                )
            )

        checks.append(
            Check(
                name="model.park_factors_weather.coverage",
                ok=True,
                detail=(
                    f"Coverage: park_factor_3yr={park_factor_3yr_rows}, "
                    f"air_density={air_density_rows}, effective_wind={effective_wind_rows} "
                    f"(total={total_rows})"
                ),
            )
        )
        return checks
