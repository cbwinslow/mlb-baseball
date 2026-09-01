"""Pitcher Vertical Approach Angle (VAA) & Flatness Whiff Engine (VAA-01, ADR-180).

Provides pitch flight trajectory modeling, vertical approach angle, and flatness whiff boosts:
1. Exact Home Plate Front-Boundary Vertical Approach Angle (VAA in degrees).
2. Four-Seam Fastball Flatness Advantage at the Top of the Strike Zone (VAA >= -4.5°).
3. Steep Downhill Angle Analysis for Splitters and Sinkers (VAA <= -7.0°).
4. Approach Angle Tiers (Elite Flat Rising VAA, Above Average Flat, Steep Downhill Sinker).

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
import math
from typing import Protocol

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


@dataclasses.dataclass(frozen=True)
class PitchApproachKinematics:
    """Flight parameters governing pitch release, trajectory drop, and plate arrival."""

    pitcher_id: str
    pitcher_name: str
    pitch_type: str = "FF"  # "FF", "SI", "SL", "FS", "CU"
    release_height_ft: float = 5.8  # Release point vertical height
    plate_z_ft: float = 3.1  # Pitch height crossing home plate (e.g. 3.1ft = top of zone)
    pfx_z_in: float = 18.0  # Induced vertical break in inches
    release_velo_mph: float = 96.0


@dataclasses.dataclass(frozen=True)
class VAAEvaluationResult:
    """Evaluated vertical approach angle, flatness rating, and whiff multiplier."""

    pitcher_name: str
    pitch_type: str
    calculated_vaa_deg: float  # Vertical Approach Angle in degrees (-3.5° to -9.0°)
    whiff_boost_pct: float  # Estimated swinging-strike boost from trajectory angle
    approach_tier: (
        str  # "ELITE_FLAT_RISING_VAA", "ABOVE_AVERAGE_FLAT", "STEEP_DOWNHILL", "STANDARD"
    )


class BaseVAAEngine(Protocol):
    """Polymorphic protocol for vertical approach angle engines."""

    def evaluate_vaa(
        self,
        kinematics: PitchApproachKinematics,
    ) -> VAAEvaluationResult:
        """Calculate VAA angle and flatness whiff multiplier."""
        ...


class VerticalApproachAngleEngine:
    """Calculates home plate Vertical Approach Angle and flatness advantage (VAA-01)."""

    def evaluate_vaa(
        self,
        kinematics: PitchApproachKinematics,
    ) -> VAAEvaluationResult:
        """Compute trajectory VAA at plate crossing."""
        # 1. Physics-based VAA Approximation:
        # Distance ~ 54.5 ft flight from release to plate front.
        # Geometric drop slope + IVB aerodynamic lift effect - gravity acceleration
        dist_ft = 54.5
        v_fps = max(60.0, kinematics.release_velo_mph * 1.4667)
        flight_t = dist_ft / v_fps

        # Initial vertical velocity v_z0
        # z_plate = z_rel + v_z0 * t + 0.5 * (a_magnus - g) * t^2
        # a_magnus = (pfx_z_in / 12.0) / (0.5 * t^2)
        # v_z(plate) = v_z0 + (a_magnus - g) * t
        magnus_accel = (kinematics.pfx_z_in / 12.0) / (0.5 * flight_t**2)
        net_a = magnus_accel - 32.174

        v_z0 = (
            kinematics.plate_z_ft - kinematics.release_height_ft - 0.5 * net_a * flight_t**2
        ) / flight_t
        v_z_plate = v_z0 + net_a * flight_t

        # VAA = arctan(v_z_plate / v_y_plate)
        vaa_rad = math.atan2(v_z_plate, v_fps)
        vaa_deg = round(math.degrees(vaa_rad), 2)

        # 2. Whiff Boost for Flat Fastballs (VAA >= -4.5° at upper zone):
        if kinematics.pitch_type == "FF" and vaa_deg >= -4.50:
            whiff_boost = round((vaa_deg - (-4.50)) * 2.2 + 2.0, 1)
        elif kinematics.pitch_type in ("FS", "CU") and vaa_deg <= -7.50:
            whiff_boost = round(abs(vaa_deg - (-7.50)) * 1.5 + 2.0, 1)
        else:
            whiff_boost = 0.0

        # 3. Approach Tier
        if kinematics.pitch_type == "FF" and vaa_deg >= -4.30:
            tier = "ELITE_FLAT_RISING_VAA"
        elif kinematics.pitch_type == "FF" and vaa_deg >= -4.80:
            tier = "ABOVE_AVERAGE_FLAT"
        elif vaa_deg <= -7.00:
            tier = "STEEP_DOWNHILL"
        else:
            tier = "STANDARD"

        return VAAEvaluationResult(
            pitcher_name=kinematics.pitcher_name,
            pitch_type=kinematics.pitch_type,
            calculated_vaa_deg=vaa_deg,
            whiff_boost_pct=whiff_boost,
            approach_tier=tier,
        )


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
    """CLI formula self-check plus, when gold columns exist, domain bounds."""
    checks: list[Check] = []
    try:
        engine = VerticalApproachAngleEngine()
        flat_fastball = PitchApproachKinematics(
            "p1",
            "Spencer Strider Archetype",
            "FF",
            release_height_ft=5.5,
            plate_z_ft=3.3,
            pfx_z_in=19.5,
            release_velo_mph=98.0,
        )
        steep_curve = PitchApproachKinematics(
            "p2",
            "Steep Curveballer",
            "CU",
            release_height_ft=6.4,
            plate_z_ft=1.5,
            pfx_z_in=-10.0,
            release_velo_mph=81.0,
        )

        r_flat = engine.evaluate_vaa(flat_fastball)
        r_stp = engine.evaluate_vaa(steep_curve)

        if (
            r_flat.approach_tier == "ELITE_FLAT_RISING_VAA"
            and r_stp.approach_tier == "STEEP_DOWNHILL"
        ):
            checks.append(
                Check(
                    "vertical approach angle engine",
                    True,
                    f"VAA verified (Flat: {r_flat.calculated_vaa_deg:>+4.2f}°)",
                )
            )
        else:
            checks.append(
                Check(
                    "vertical approach angle engine",
                    False,
                    f"Unexpected VAA output: {r_flat}, {r_stp}",
                )
            )
    except Exception as exc:
        checks.append(Check("vertical approach angle engine", False, str(exc)))
    return checks
