"""Pitcher Physical Extension & Effective Perceived Velocity Engine (EXT-01, ADR-153).

Provides physical stride extension modeling, time-to-plate kinematics, and perceived velocity:
1. Physical Release Extension (distance down the mound towards home plate in feet).
2. Time-to-Plate Optical Reaction Kinematics (flight duration from release to contact zone).
3. Effective Perceived Velocity (translates reaction time into perceived radar velocity).
4. Pitcher Extension Tiers (Elite Long Stride, Standard, Short/Compact).

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class PitcherExtensionProfile:
    """Pitcher physical release extension and pitch radar speed."""

    pitcher_id: str
    pitcher_name: str
    release_extension_ft: float = 6.2  # MLB avg ~6.2 ft
    radar_velocity_mph: float = 94.0


@dataclasses.dataclass(frozen=True)
class EffectiveVelocityResult:
    """Calculated reaction time, effective perceived velocity, and extension grade."""

    pitcher_name: str
    radar_velocity_mph: float
    release_extension_ft: float
    time_to_plate_ms: float  # milliseconds from release to contact zone
    perceived_velocity_mph: float  # effective perceived speed
    velocity_delta_mph: float  # perceived - radar (positive for long extension)
    extension_tier: str  # "ELITE_LONG", "AVERAGE", "SHORT_COMPACT"


class BaseExtensionEngine(Protocol):
    """Polymorphic protocol for extension and effective velocity engines."""

    def evaluate_effective_velocity(
        self,
        profile: PitcherExtensionProfile,
    ) -> EffectiveVelocityResult:
        """Calculate optical time-to-plate and effective velocity."""
        ...


class PitcherExtensionEngine:
    """Calculates pitcher extension kinematics and effective velocity (EXT-01)."""

    def evaluate_effective_velocity(
        self,
        profile: PitcherExtensionProfile,
    ) -> EffectiveVelocityResult:
        """Compute flight duration and perceived velocity adjustment."""
        # 1. Physical Flight Distance:
        # Rubber is 60.5 ft from back of home plate; contact zone ~ 1.4 ft in front
        # Total distance from release to plate = 60.5 - extension - 1.4
        flight_dist_ft = 60.5 - profile.release_extension_ft - 1.4

        # 2. Flight Duration in seconds:
        # v (ft/s) = v (mph) * 1.46667
        # Average velocity drops by ~9% due to air drag over flight, so v_avg ~ v_release * 0.955
        v_fps = profile.radar_velocity_mph * 1.46667 * 0.955
        time_to_plate_s = flight_dist_ft / max(10.0, v_fps)
        time_to_plate_ms = round(time_to_plate_s * 1000.0, 1)

        # 3. Effective Velocity Adjustment (Perry Husband / Statcast model):
        # Baseline reference extension = 6.2 ft (MLB average)
        # Every +1.0 ft of extension adds ~ +1.25 mph in perceived speed
        velo_delta = round((profile.release_extension_ft - 6.2) * 1.25, 2)
        perceived_velo = round(profile.radar_velocity_mph + velo_delta, 2)

        # 4. Extension tier
        if profile.release_extension_ft >= 7.0:
            tier = "ELITE_LONG"
        elif profile.release_extension_ft <= 5.7:
            tier = "SHORT_COMPACT"
        else:
            tier = "AVERAGE"

        return EffectiveVelocityResult(
            pitcher_name=profile.pitcher_name,
            radar_velocity_mph=profile.radar_velocity_mph,
            release_extension_ft=profile.release_extension_ft,
            time_to_plate_ms=time_to_plate_ms,
            perceived_velocity_mph=perceived_velo,
            velocity_delta_mph=velo_delta,
            extension_tier=tier,
        )


def health_check() -> list[Check]:
    """Operational health check for the Pitcher Extension Engine (EXT-01)."""
    checks: list[Check] = []
    try:
        engine = PitcherExtensionEngine()
        tall_pitcher = PitcherExtensionProfile(
            "p1", "Tall Long Stride", release_extension_ft=7.4, radar_velocity_mph=95.0
        )

        res = engine.evaluate_effective_velocity(tall_pitcher)

        if res.extension_tier == "ELITE_LONG" and res.perceived_velocity_mph > 96.0:
            checks.append(
                Check(
                    "pitcher extension engine",
                    True,
                    f"Extension verified (Perceived: {res.perceived_velocity_mph:.1f}mph)",
                )
            )
        else:
            checks.append(
                Check("pitcher extension engine", False, f"Unexpected extension evaluation: {res}")
            )
    except Exception as exc:
        checks.append(Check("pitcher extension engine", False, str(exc)))
    return checks
