"""Pitcher Arm Slot Stability Across Arsenal Pitches Engine (ARM-ALIGN-01, ADR-220).

Provides multi-pitch arm angle consistency, release height dispersion, and pitch tipping defense:
1. Arsenal Arm Alignment Rating (AAAR score measuring slot identity across pitch families).
2. Pitch Tipping Risk Multiplier (identifies visual mechanical tells from dropped elbows).
3. Alignment Archetypes (Deceptive Tunneled Arm Slot Clone, Tell-Prone Dropped Elbow Alert).

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class PitcherArsenalArmSlotMetrics:
    """Observed pitcher arm angles and release heights across Fastball, Breaking, and Offspeed."""

    pitcher_id: str
    pitcher_name: str
    fastball_arm_angle_deg: float = 42.0
    breaking_arm_angle_deg: float = 43.5
    offspeed_arm_angle_deg: float = 41.0
    fastball_rel_z_in: float = 68.0
    breaking_rel_z_in: float = 66.8
    offspeed_rel_z_in: float = 68.5
    pitch_count_evaluated: int = 250


@dataclasses.dataclass(frozen=True)
class ArmAlignEvaluationResult:
    """Evaluated arm slot alignment, maximum gap, AAAR score, and tipping risk multiplier."""

    pitcher_name: str
    max_arm_angle_gap_deg: float  # Max delta between any 2 pitch types (deg)
    max_rel_z_gap_in: float  # Max delta between release heights (in)
    aaar_score: float  # Arsenal Arm Alignment Rating (0 to 160)
    tipping_risk_multiplier: float  # Multiplier on batter recognition speed (1.00x to 1.45x)
    alignment_tier: str  # e.g. "DECEPTIVE_TUNNELED_ARM_SLOT_CLONE", "TELL_PRONE_DROPPED_ELBOW"
    is_slot_clone: bool


class BaseArmAlignEngine(Protocol):
    """Polymorphic protocol for arm slot alignment engines."""

    def evaluate_alignment(
        self,
        metrics: PitcherArsenalArmSlotMetrics,
    ) -> ArmAlignEvaluationResult:
        """Calculate AAAR score, tipping multiplier, and alignment tier."""
        ...


class PitcherArmAlignEngine:
    """Calculates multi-pitch arm angle consistency and release height AAAR (ARM-ALIGN-01)."""

    def evaluate_alignment(
        self,
        metrics: PitcherArsenalArmSlotMetrics,
    ) -> ArmAlignEvaluationResult:
        """Compute max arm slot gap and AAAR rating."""
        # Calculate max angle discrepancy across the 3 families
        angles = [
            metrics.fastball_arm_angle_deg,
            metrics.breaking_arm_angle_deg,
            metrics.offspeed_arm_angle_deg,
        ]
        max_angle_gap = round(max(angles) - min(angles), 2)

        # Calculate max release height discrepancy in inches
        heights = [
            metrics.fastball_rel_z_in,
            metrics.breaking_rel_z_in,
            metrics.offspeed_rel_z_in,
        ]
        max_z_gap = round(max(heights) - min(heights), 2)

        # AAAR Score: benchmark 3.5 deg max angle gap, 2.5 in max Z gap
        angle_bonus = (3.5 - max_angle_gap) * 8.0
        z_bonus = (2.5 - max_z_gap) * 7.0
        aaar = round(max(0.0, 100.0 + angle_bonus + z_bonus), 1)

        # Tipping Risk Multiplier
        excess_deg = max(0.0, max_angle_gap - 5.0)
        excess_z = max(0.0, max_z_gap - 3.5)
        tip_mult = round(1.0 + (excess_deg * 0.06 + excess_z * 0.04), 3)

        is_clone = aaar >= 116.0 and max_angle_gap <= 1.80 and max_z_gap <= 1.30

        # Tiers
        if is_clone:
            tier = "DECEPTIVE_TUNNELED_ARM_SLOT_CLONE"
        elif max_angle_gap >= 6.50 or max_z_gap >= 4.50:
            tier = "TELL_PRONE_DROPPED_ELBOW_ALERT"
        elif max_angle_gap <= 2.80 and max_z_gap <= 2.00:
            tier = "SOLID_CONSISTENT_ARM_SLOT"
        else:
            tier = "AVERAGE_ARM_SLOT_VARIANCE"

        return ArmAlignEvaluationResult(
            pitcher_name=metrics.pitcher_name,
            max_arm_angle_gap_deg=max_angle_gap,
            max_rel_z_gap_in=max_z_gap,
            aaar_score=aaar,
            tipping_risk_multiplier=tip_mult,
            alignment_tier=tier,
            is_slot_clone=is_clone,
        )


def health_check() -> list[Check]:
    """Operational health check for Pitcher Arm Align Engine (ARM-ALIGN-01)."""
    checks: list[Check] = []
    try:
        engine = PitcherArmAlignEngine()
        clone = PitcherArsenalArmSlotMetrics(
            "p1", "Spencer Strider", 42.0, 42.6, 41.8, 68.0, 67.5, 68.2, 280
        )
        tell = PitcherArsenalArmSlotMetrics(
            "p2", "Tipping Pitcher", 45.0, 37.0, 44.0, 70.0, 64.0, 69.0, 200
        )

        r_clo = engine.evaluate_alignment(clone)
        r_tel = engine.evaluate_alignment(tell)

        if (
            r_clo.alignment_tier == "DECEPTIVE_TUNNELED_ARM_SLOT_CLONE"
            and r_tel.alignment_tier == "TELL_PRONE_DROPPED_ELBOW_ALERT"
        ):
            checks.append(
                Check(
                    "arm align engine",
                    True,
                    f"Arm Align verified (Strider AAAR: {r_clo.aaar_score:.1f})",
                )
            )
        else:
            checks.append(
                Check("arm align engine", False, f"Unexpected arm align output: {r_clo}, {r_tel}")
            )
    except Exception as exc:
        checks.append(Check("arm align engine", False, str(exc)))
    return checks
