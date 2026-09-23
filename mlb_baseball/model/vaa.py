"""Pitcher Vertical Approach Angle (VAA) at the front of home plate (VAA-01, ADR-180).

`pitch_vaa_degrees()` / `compute()` is the real, cited, gold-integrated
formula from Statcast kinematics (vy0/ay/vz0/az). A separate uncited
scouting-input approximation (`ApproximateVAAEngine`, ex-`vaa_flatness_engine`
in the metric catalog) backed the CLI `mlb vaa` command and was removed --
no real published equivalent was found for it (metric-catalog triage,
2026-09-23); this module now has one VAA calculator, not two.
"""

from __future__ import annotations

import math

import psycopg

from mlb_baseball.db import fetch_one
from mlb_baseball.health import Check
from mlb_baseball.sql import read_sql

# Statcast kinematics origin and the front of home plate (feet).
# Chamberlain / Pavlidis, FanGraphs 2022-02-01.
_Y0_FT = 50.0
_YF_FT = 17.0 / 12.0
MIN_STARTER_FF = 20


def pitch_vaa_degrees(*, vy0: float, ay: float, vz0: float, az: float) -> float | None:
    """Vertical approach angle at the front of the plate, degrees.

    Published formula (Alex Chamberlain, FanGraphs, 1 Feb 2022, crediting
    Harry Pavlidis / baseball physicists), using Statcast velocities and
    accelerations measured at y = 50 ft:

        vy_f = -sqrt(vy0² - 2·ay·(y0 - yf))
        t    = (vy_f - vy0) / ay
        vz_f = vz0 + az·t
        VAA  = -arctan(vz_f / vy_f) · (180/π)

    y0 = 50, yf = 17/12 (front of the plate). Typical four-seam VAA is
    about −4.5° to −6°. Returns None when the kinematics are unusable
    (zero ay, negative discriminant, zero plate-y velocity).

    This is the real formula, from measured Statcast acceleration
    components -- not `ApproximateVAAEngine.evaluate_vaa()`'s scouting-input
    approximation elsewhere in this module (see module docstring).
    """
    if ay == 0.0:
        return None
    disc = vy0 * vy0 - 2.0 * ay * (_Y0_FT - _YF_FT)
    if disc <= 0.0:
        return None
    vy_f = -math.sqrt(disc)
    if vy_f == 0.0:
        return None
    t = (vy_f - vy0) / ay
    vz_f = vz0 + az * t
    return round(math.degrees(-math.atan(vz_f / vy_f)), 4)


def compute(conn: psycopg.Connection) -> int:
    """Entering four-seam VAA (degrees) for each game's listed starters.

    Point-in-time: only prior games in the same season. NULL below
    MIN_STARTER_FF pitches. Missing Statcast kinematics → 0 rows, not crash.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.statcast_pitch')")
        (exists,) = fetch_one(cur)
        if not exists:
            return 0
        cur.execute(
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_schema = 'raw' AND table_name = 'statcast_pitch' "
            "  AND column_name IN ('vy0', 'ay', 'vz0', 'az')"
        )
        (n,) = fetch_one(cur)
        if n != 4:
            return 0
        cur.execute(
            read_sql("starter_vaa_update.sql"),
            {"min_ff": MIN_STARTER_FF},
        )
        return cur.rowcount


def health_check() -> list[Check]:
    """Self-check the real Chamberlain/Pavlidis VAA formula against a typical
    modern four-seam fastball's Statcast kinematics (expected -4.5 to -6.0deg,
    per the module docstring) and confirm degenerate input returns None."""
    checks: list[Check] = []
    try:
        typical_ff = pitch_vaa_degrees(vy0=-130.0, ay=25.5, vz0=-5.8, az=-17.5)
        degenerate = pitch_vaa_degrees(vy0=-130.0, ay=0.0, vz0=-5.8, az=-17.5)
        if typical_ff is not None and -6.5 <= typical_ff <= -4.0 and degenerate is None:
            checks.append(
                Check(
                    "vertical approach angle formula",
                    True,
                    f"VAA verified (typical FF: {typical_ff:>+4.2f} deg)",
                )
            )
        else:
            checks.append(
                Check(
                    "vertical approach angle formula",
                    False,
                    f"Unexpected VAA output: typical={typical_ff}, degenerate={degenerate}",
                )
            )
    except Exception as exc:
        checks.append(Check("vertical approach angle formula", False, str(exc)))
    return checks
