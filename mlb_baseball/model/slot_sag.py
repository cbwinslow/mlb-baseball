"""Pitcher Arm Slot Fatigue Sag & Lateral Drift Engine (SLOT-SAG-01, ADR-252).

Provides late-outing arm slot drop, release point widening, and ASFSI index:
1. Arm Slot Fatigue Sag Index (ASFSI score measuring arm slot stability).
2. Fatigue Sag Damage Runs Saved (FSDRS net defensive runs saved from slot consistency).
3. Slot Sag Archetypes (Iron Shoulder Replicator, Collapsing Slot Liability).

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class PitcherSlotSagMetrics:
    """Observed early vs late arm slot angle and lateral release coordinates."""

    pitcher_id: str
    pitcher_name: str
    early_arm_slot_angle_deg: float = 45.0  # Slot angle early in outing (deg)
    late_arm_slot_angle_deg: float = 43.5  # Slot angle after pitch 75+ (deg)
    early_release_x_in: float = -24.0  # Lateral release early (in)
    late_release_x_in: float = -25.2  # Lateral release late (in)
    late_pitches_thrown: int = 35


@dataclasses.dataclass(frozen=True)
class SlotSagEvaluationResult:
    """Evaluated arm slot fatigue score, runs saved, and stability tier."""

    pitcher_name: str
    asfsi_score: float  # Arm Slot Fatigue Sag Index (0 to 160)
    fsdrs_runs_saved: float  # Net defensive runs saved via slot stability
    sag_tier: (
        str  # e.g. "IRON_SHOULDER_SLOT_REPLICATOR", "COLLAPSING_SLOT_DROPPING_FATIGUE_LIABILITY"
    )
    is_slot_replicator: bool


class BaseSlotSagEngine(Protocol):
    """Polymorphic protocol for arm slot fatigue sag engines."""

    def evaluate_slot_sag(
        self,
        metrics: PitcherSlotSagMetrics,
    ) -> SlotSagEvaluationResult:
        """Calculate ASFSI rating, FSDRS runs, and stability tier."""
        ...


class PitcherSlotSagEngine:
    """Calculates arm slot sag angle drop, lateral release drift, and ASFSI (SLOT-SAG-01)."""

    def evaluate_slot_sag(
        self,
        metrics: PitcherSlotSagMetrics,
    ) -> SlotSagEvaluationResult:
        """Compute ASFSI score and late-outing runs saved."""
        angle_drop = max(0.0, metrics.early_arm_slot_angle_deg - metrics.late_arm_slot_angle_deg)
        drift_x = abs(metrics.late_release_x_in - metrics.early_release_x_in)

        # ASFSI Score: benchmark 1.5 deg drop, 1.2 in drift
        angle_bonus = (1.5 - angle_drop) * 8.0
        drift_bonus = (1.2 - drift_x) * 6.0
        asfsi = round(max(0.0, 100.0 + angle_bonus + drift_bonus), 1)

        # FSDRS Runs (~0.0035 runs per late pitch per point above 100)
        pitches = max(1, metrics.late_pitches_thrown)
        runs = round((asfsi - 100.0) * (pitches * 0.0035), 2)

        is_rep = asfsi >= 114.0 and angle_drop <= 0.8 and drift_x <= 0.8

        # Tiers
        if is_rep:
            tier = "IRON_SHOULDER_SLOT_REPLICATOR"
        elif angle_drop >= 4.5 or drift_x >= 3.8:
            tier = "COLLAPSING_SLOT_DROPPING_FATIGUE_LIABILITY"
        elif angle_drop <= 1.8 and drift_x <= 1.5:
            tier = "SOLID_ARM_SLOT_STABILITY"
        else:
            tier = "AVERAGE_ARM_SLOT_STABILITY"

        return SlotSagEvaluationResult(
            pitcher_name=metrics.pitcher_name,
            asfsi_score=asfsi,
            fsdrs_runs_saved=runs,
            sag_tier=tier,
            is_slot_replicator=is_rep,
        )


def health_check() -> list[Check]:
    """Operational health check for Pitcher Slot Sag Engine (SLOT-SAG-01)."""
    checks: list[Check] = []
    try:
        engine = PitcherSlotSagEngine()
        replicator = PitcherSlotSagMetrics("p1", "Zack Wheeler", 44.0, 43.8, -22.0, -22.3, 40)
        collapsing = PitcherSlotSagMetrics("p2", "Fatigued Arm", 48.0, 42.0, -20.0, -25.5, 30)

        r_rep = engine.evaluate_slot_sag(replicator)
        r_col = engine.evaluate_slot_sag(collapsing)

        if (
            r_rep.sag_tier == "IRON_SHOULDER_SLOT_REPLICATOR"
            and r_col.sag_tier == "COLLAPSING_SLOT_DROPPING_FATIGUE_LIABILITY"
        ):
            checks.append(
                Check(
                    "slot sag engine",
                    True,
                    f"Slot Sag verified (Wheeler ASFSI: {r_rep.asfsi_score:.1f})",
                )
            )
        else:
            checks.append(
                Check(
                    "slot sag engine",
                    False,
                    f"Unexpected slot sag output: {r_rep}, {r_col}",
                )
            )
    except Exception as exc:
        checks.append(Check("slot sag engine", False, str(exc)))
    return checks
