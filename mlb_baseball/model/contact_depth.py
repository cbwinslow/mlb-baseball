"""Batter Contact Depth & Point-of-Impact Kinematics Engine (CONTACT-DEPTH-01, ADR-191).

Provides point-of-impact spatial depth, swing timing, and spray optimization modeling:
1. Contact Depth Relative to Home Plate Front Edge (y_contact in inches).
2. Velocity and Location-Adjusted Optimal Contact Point (y_opt in inches).
3. Timing Deficit Margin and Exit Velocity Impact Multiplier.
4. Depth Archetypes (Out-Front Pull Crusher, Deep-Zone Oppo Specialist, Optimal Contact).

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class ContactKinematicsInput:
    """Observed spatial point of impact and pitch context parameters."""

    batter_id: str
    batter_name: str
    contact_y_inches: float = 6.5  # Inches relative to front edge of home plate
    pitch_velo_mph: float = 94.0
    pitch_location_x_inches: float = -3.0  # Inside pitch for RHB
    spray_angle_deg: float = -25.0  # Pulled for RHB
    exit_velo_mph: float = 102.0
    batter_side: str = "R"


@dataclasses.dataclass(frozen=True)
class ContactDepthEvaluationResult:
    """Evaluated contact depth margin, timing efficiency, and depth tier."""

    batter_name: str
    contact_depth_in: float
    optimal_depth_in: float
    depth_margin_in: float  # y_contact - y_opt
    timing_efficiency_pct: float
    depth_tier: str  # e.g. "OUT_FRONT_PULL_CRUSHER", "OPTIMAL_ZONE_CONTACT"
    is_out_front_slugger: bool


class BaseContactDepthEngine(Protocol):
    """Polymorphic protocol for contact depth kinematics engines."""

    def evaluate_contact(
        self,
        kinematics: ContactKinematicsInput,
    ) -> ContactDepthEvaluationResult:
        """Calculate contact depth margin, timing efficiency, and tier."""
        ...


class ContactDepthEngine:
    """Calculates point-of-impact depth kinematics and swing timing (CONTACT-DEPTH-01)."""

    def evaluate_contact(
        self,
        kinematics: ContactKinematicsInput,
    ) -> ContactDepthEvaluationResult:
        """Compute optimal contact depth and timing efficiency."""
        # 1. Optimal Point of Impact:
        # Higher velo and inside pitches require catching the ball further in front of the plate
        inside_factor = (
            -kinematics.pitch_location_x_inches
            if kinematics.batter_side == "R"
            else kinematics.pitch_location_x_inches
        )
        y_opt = (
            5.0 + ((kinematics.pitch_velo_mph - 90.0) / 10.0) * 1.5 + (inside_factor / 10.0) * 2.0
        )
        y_opt = round(y_opt, 2)

        # 2. Timing Margin:
        margin = round(kinematics.contact_y_inches - y_opt, 2)

        # 3. Timing Efficiency %
        eff = max(0.0, 1.0 - (abs(margin) / 8.0) ** 2 * 0.30) * 100.0
        eff = round(min(100.0, eff), 1)

        # 4. Out-Front Flag
        is_front = kinematics.contact_y_inches >= 6.0 and kinematics.exit_velo_mph >= 98.0

        # 5. Depth Tiers
        if is_front and kinematics.spray_angle_deg <= -15.0:
            tier = "OUT_FRONT_PULL_CRUSHER"
        elif kinematics.contact_y_inches <= -1.5:
            tier = "DEEP_ZONE_OPPO_SPECIALIST"
        elif margin <= -4.5:
            tier = "LATE_TIMING_VULNERABILITY"
        elif abs(margin) <= 2.0:
            tier = "OPTIMAL_ZONE_CONTACT"
        else:
            tier = "AVERAGE"

        return ContactDepthEvaluationResult(
            batter_name=kinematics.batter_name,
            contact_depth_in=kinematics.contact_y_inches,
            optimal_depth_in=y_opt,
            depth_margin_in=margin,
            timing_efficiency_pct=eff,
            depth_tier=tier,
            is_out_front_slugger=is_front,
        )


def health_check() -> list[Check]:
    """Operational health check for Contact Depth Kinematics Engine (CONTACT-DEPTH-01)."""
    checks: list[Check] = []
    try:
        engine = ContactDepthEngine()
        crusher = ContactKinematicsInput("b1", "Pull Crusher", 7.5, 95.0, -4.0, -28.0, 104.5, "R")
        late_hitter = ContactKinematicsInput("b2", "Late Hitter", 0.0, 98.0, -2.0, 15.0, 84.0, "R")

        r_cru = engine.evaluate_contact(crusher)
        r_lat = engine.evaluate_contact(late_hitter)

        if (
            r_cru.depth_tier == "OUT_FRONT_PULL_CRUSHER"
            and r_lat.depth_tier == "LATE_TIMING_VULNERABILITY"
        ):
            checks.append(
                Check(
                    "contact depth engine",
                    True,
                    f"Contact depth verified (Depth: {r_cru.contact_depth_in:>+4.1f} in)",
                )
            )
        else:
            checks.append(
                Check("contact depth engine", False, f"Unexpected contact depth: {r_cru}, {r_lat}")
            )
    except Exception as exc:
        checks.append(Check("contact depth engine", False, str(exc)))
    return checks
