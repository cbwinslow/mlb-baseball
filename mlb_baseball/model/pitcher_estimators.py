"""Advanced Pitcher Estimators (xFIP, SIERA) and Batter-vs-Pitcher Platoon Splits.

Computes point-in-time entering xFIP, SIERA, and handedness splits for starting
pitchers and bullpens (PIT-06, PLN-03, ADR-090).
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
MIN_PLATOON_PA = 15


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
            "  AND column_name = 'bat_hand_cd'"
        )
        if not cur.fetchone():
            return 0
        cur.execute(
            read_sql("team_pitcher_estimators_retrosheet_update.sql"),
            {
                "min_starter_pa": MIN_STARTER_PA,
                "min_bullpen_pa": MIN_BULLPEN_PA,
                "min_platoon_pa": MIN_PLATOON_PA,
            },
        )
        return cur.rowcount


def health_check() -> list[Check]:
    with get_connection() as conn, conn.cursor() as cur:
        conn.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
        cur.execute(read_sql("team_pitcher_estimators_health_check.sql"))
        row = cur.fetchone()
        if not row:
            return [
                Check(
                    name="model.pitcher_estimators",
                    ok=False,
                    detail="No rows returned by team_pitcher_estimators_health_check.sql",
                )
            ]

        (
            total_rows,
            home_starter_xfip_rows,
            away_starter_xfip_rows,
            home_starter_siera_rows,
            away_starter_siera_rows,
            home_starter_vs_lhb_woba_rows,
            away_starter_vs_lhb_woba_rows,
            home_starter_vs_rhb_woba_rows,
            away_starter_vs_rhb_woba_rows,
            home_starter_vs_lhb_k_pct_rows,
            away_starter_vs_lhb_k_pct_rows,
            home_starter_vs_rhb_k_pct_rows,
            away_starter_vs_rhb_k_pct_rows,
            home_bullpen_xfip_rows,
            away_bullpen_xfip_rows,
            home_bullpen_siera_rows,
            away_bullpen_siera_rows,
            home_starter_xfip_oob,
            away_starter_xfip_oob,
            home_starter_siera_oob,
            away_starter_siera_oob,
            home_bullpen_xfip_oob,
            away_bullpen_xfip_oob,
            home_bullpen_siera_oob,
            away_bullpen_siera_oob,
            home_vs_lhb_k_pct_oob,
            away_vs_lhb_k_pct_oob,
            home_vs_rhb_k_pct_oob,
            away_vs_rhb_k_pct_oob,
            home_vs_lhb_woba_oob,
            away_vs_lhb_woba_oob,
            home_vs_rhb_woba_oob,
            away_vs_rhb_woba_oob,
        ) = row

        oob_total = sum(
            [
                home_starter_xfip_oob,
                away_starter_xfip_oob,
                home_starter_siera_oob,
                away_starter_siera_oob,
                home_bullpen_xfip_oob,
                away_bullpen_xfip_oob,
                home_bullpen_siera_oob,
                away_bullpen_siera_oob,
                home_vs_lhb_k_pct_oob,
                away_vs_lhb_k_pct_oob,
                home_vs_rhb_k_pct_oob,
                away_vs_rhb_k_pct_oob,
                home_vs_lhb_woba_oob,
                away_vs_lhb_woba_oob,
                home_vs_rhb_woba_oob,
                away_vs_rhb_woba_oob,
            ]
        )

        checks = []
        if oob_total > 0:
            checks.append(
                Check(
                    name="model.pitcher_estimators.domain",
                    ok=False,
                    detail=(
                        f"{oob_total} pitcher estimator / platoon values were "
                        "outside valid domain bounds"
                    ),
                )
            )
        else:
            checks.append(
                Check(
                    name="model.pitcher_estimators.domain",
                    ok=True,
                    detail="All pitcher estimator and platoon split values within domain bounds",
                )
            )

        checks.append(
            Check(
                name="model.pitcher_estimators.coverage",
                ok=(home_starter_xfip_rows > 0 or total_rows == 0),
                detail=(
                    f"Populated games: starter xFIP={home_starter_xfip_rows}/{total_rows}, "
                    f"bullpen SIERA={home_bullpen_siera_rows}/{total_rows}, "
                    f"starter vs LHB wOBA={home_starter_vs_lhb_woba_rows}/{total_rows}"
                ),
            )
        )

        return checks
