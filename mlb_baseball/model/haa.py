"""Pitcher Horizontal Approach Angle (HAA) & Cross-Body Deception Engine (HAA-01, ADR-184).

Provides horizontal plate entry trajectory, cross-body release, and east-west movement modeling:
1. Exact Home Plate Front-Boundary Horizontal Approach Angle (HAA in degrees).
2. Cross-Body Release Deception Score (combining wide release point with extreme entry angle).
3. Extreme Sweeper and Arm-Side Sinker Trajectory Analysis (|HAA| >= 3.0°).
4. Approach Angle Tiers (Extreme Cross-Fire Sweep, Above Average East-West, Standard).

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
import math
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class PitchHorizontalKinematics:
    """Flight parameters governing horizontal release offset, side break, and plate arrival."""

    pitcher_id: str
    pitcher_name: str
    pitch_type: str = "ST"  # "ST", "SL", "SI", "CH", "FF"
    release_x_ft: float = -2.5  # Negative = Right-handed release from 1B side
    plate_x_ft: float = 0.8  # Positive = Glove-side outside corner
    pfx_x_in: float = 16.0  # Horizontal break in inches
    release_velo_mph: float = 84.0


@dataclasses.dataclass(frozen=True)
class HAAEvaluationResult:
    """Evaluated horizontal approach angle, deception score, and approach tier."""

    pitcher_name: str
    pitch_type: str
    calculated_haa_deg: float  # Horizontal Approach Angle in degrees (-4.5° to +4.5°)
    cross_body_deception_score: float  # Composite deception rating out of 100
    haa_tier: str  # "EXTREME_CROSS_FIRE_SWEEP", "ABOVE_AVERAGE_EAST_WEST", "STANDARD"


class BaseHAAEngine(Protocol):
    """Polymorphic protocol for horizontal approach angle engines."""

    def evaluate_haa(
        self,
        kinematics: PitchHorizontalKinematics,
    ) -> HAAEvaluationResult:
        """Calculate HAA angle and cross-body deception score."""
        ...


class HorizontalApproachAngleEngine:
    """Calculates home plate Horizontal Approach Angle and deception score (HAA-01)."""

    def evaluate_haa(
        self,
        kinematics: PitchHorizontalKinematics,
    ) -> HAAEvaluationResult:
        """Compute trajectory HAA at plate crossing."""
        # 1. Physics-based HAA Approximation:
        # Distance ~ 54.5 ft flight from release to plate front.
        dist_ft = 54.5
        v_fps = max(60.0, kinematics.release_velo_mph * 1.4667)
        flight_t = dist_ft / v_fps

        # Initial horizontal velocity v_x0 and magnus side acceleration
        magnus_x_accel = (kinematics.pfx_x_in / 12.0) / (0.5 * flight_t**2)
        v_x0 = (
            kinematics.plate_x_ft - kinematics.release_x_ft - 0.5 * magnus_x_accel * flight_t**2
        ) / flight_t
        v_x_plate = v_x0 + magnus_x_accel * flight_t

        # HAA = arctan(v_x_plate / v_y_plate)
        haa_rad = math.atan2(v_x_plate, v_fps)
        haa_deg = round(math.degrees(haa_rad), 2)

        # 2. Cross-Body Deception Score (0 to 100)
        # Wide release (|x_rel| >= 2.2ft) combined with sharp entry angle
        deception = round(min(100.0, abs(kinematics.release_x_ft) * 18.0 + abs(haa_deg) * 12.0), 1)

        # 3. Approach Tier
        if abs(haa_deg) >= 3.0 and abs(kinematics.release_x_ft) >= 2.0:
            tier = "EXTREME_CROSS_FIRE_SWEEP"
        elif abs(haa_deg) >= 2.0:
            tier = "ABOVE_AVERAGE_EAST_WEST"
        else:
            tier = "STANDARD"

        return HAAEvaluationResult(
            pitcher_name=kinematics.pitcher_name,
            pitch_type=kinematics.pitch_type,
            calculated_haa_deg=haa_deg,
            cross_body_deception_score=deception,
            haa_tier=tier,
        )


def health_check() -> list[Check]:
    """Operational health check for Horizontal Approach Angle Engine (HAA-01)."""
    checks: list[Check] = []
    try:
        engine = HorizontalApproachAngleEngine()
        sweeper_ace = PitchHorizontalKinematics(
            "p1",
            "Sweeper Ace",
            "ST",
            release_x_ft=-2.8,
            plate_x_ft=0.9,
            pfx_x_in=18.0,
            release_velo_mph=84.0,
        )
        straight_over = PitchHorizontalKinematics(
            "p2",
            "Overhand Pitcher",
            "FF",
            release_x_ft=-0.8,
            plate_x_ft=0.1,
            pfx_x_in=3.0,
            release_velo_mph=94.0,
        )

        r_sw = engine.evaluate_haa(sweeper_ace)
        r_ov = engine.evaluate_haa(straight_over)

        if r_sw.haa_tier == "EXTREME_CROSS_FIRE_SWEEP" and r_ov.haa_tier == "STANDARD":
            checks.append(
                Check(
                    "horizontal approach angle engine",
                    True,
                    f"HAA verified (HAA: {r_sw.calculated_haa_deg:>+4.2f}°)",
                )
            )
        else:
            checks.append(
                Check(
                    "horizontal approach angle engine",
                    False,
                    f"Unexpected HAA output: {r_sw}, {r_ov}",
                )
            )
    except Exception as exc:
        checks.append(Check("horizontal approach angle engine", False, str(exc)))
    return checks
