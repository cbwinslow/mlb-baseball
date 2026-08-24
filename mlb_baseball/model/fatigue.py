"""Pitcher Acute-to-Chronic Workload & Fatigue Risk Engine (FATIGUE-01, ADR-161).

Provides multi-week rolling workload tracking and biomechanical fatigue indicators:
1. Acute-to-Chronic Workload Ratio (ACWR) (7-day Acute Load vs 28-day Chronic Base).
2. Fastball Radar Velocity Decay Detection (Delta velo <= -1.2 mph).
3. Vertical Release Point Arm Slot Sagging Detection (Delta z <= -1.5 in).
4. Composite Pitcher Fatigue Risk Index (FRI) and Rotation Optimization Alerts.

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

import numpy as np

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class PitcherWorkloadMetrics:
    """Multi-week rolling workload and biomechanical tracking metrics."""

    pitcher_id: str
    pitcher_name: str
    pitches_7d: int = 95
    pitches_28d: int = 340
    velo_delta_mph: float = 0.0  # Recent fastball velo minus season baseline
    release_drop_in: float = 0.0  # Vertical release height delta (inches)
    high_stress_innings_count: int = 1  # 25+ pitches or heavy RISP load


@dataclasses.dataclass(frozen=True)
class PitcherFatigueEvaluation:
    """Evaluated workload strain, acute fatigue ratio, and risk classification."""

    pitcher_name: str
    acwr_ratio: float
    fatigue_risk_index: float  # 0.0 to 100.0
    fatigue_tier: str  # "HIGH_FATIGUE_OVERLOAD", "MODERATE_FATIGUE", "OPTIMAL_FITNESS"
    is_velocity_flagged: bool
    is_biomechanics_flagged: bool


class BaseFatigueEngine(Protocol):
    """Polymorphic protocol for pitcher workload fatigue engines."""

    def evaluate_fatigue(
        self,
        metrics: PitcherWorkloadMetrics,
    ) -> PitcherFatigueEvaluation:
        """Calculate ACWR workload ratio and composite fatigue risk index."""
        ...


class PitcherFatigueEngine:
    """Evaluates multi-week pitcher workload strain and biomechanical fatigue (FATIGUE-01)."""

    def evaluate_fatigue(
        self,
        metrics: PitcherWorkloadMetrics,
    ) -> PitcherFatigueEvaluation:
        """Compute ACWR and composite fatigue risk index."""
        # 1. Acute vs Chronic Workload Ratio:
        # Acute: avg pitches/day in last 7 days
        # Chronic: avg pitches/day in last 28 days
        acute_daily = metrics.pitches_7d / 7.0
        chronic_daily = metrics.pitches_28d / 28.0
        acwr = round(acute_daily / max(1.0, chronic_daily), 2)

        # 2. Velocity decay flag: velo drop >= 1.2 mph
        velo_flag = metrics.velo_delta_mph <= -1.2

        # 3. Biomechanics release point drop flag: vertical drop >= 1.5 inches
        mech_flag = metrics.release_drop_in <= -1.5

        # 4. Composite Fatigue Risk Index (0 to 100):
        # Base from ACWR overload
        acwr_penalty = max(0.0, (acwr - 1.0) / 0.5) * 35.0
        velo_penalty = max(0.0, -metrics.velo_delta_mph) * 20.0
        mech_penalty = max(0.0, -metrics.release_drop_in) * 6.0
        stress_penalty = metrics.high_stress_innings_count * 5.0

        raw_fri = acwr_penalty + velo_penalty + mech_penalty + stress_penalty
        fri = round(float(np.clip(raw_fri, 0.0, 100.0)), 1)

        # 5. Fatigue Tier
        if fri >= 60.0 or (velo_flag and mech_flag):
            tier = "HIGH_FATIGUE_OVERLOAD"
        elif fri >= 35.0:
            tier = "MODERATE_FATIGUE"
        else:
            tier = "OPTIMAL_FITNESS"

        return PitcherFatigueEvaluation(
            pitcher_name=metrics.pitcher_name,
            acwr_ratio=acwr,
            fatigue_risk_index=fri,
            fatigue_tier=tier,
            is_velocity_flagged=velo_flag,
            is_biomechanics_flagged=mech_flag,
        )


def health_check() -> list[Check]:
    """Operational health check for the Pitcher Fatigue Engine (FATIGUE-01)."""
    checks: list[Check] = []
    try:
        engine = PitcherFatigueEngine()
        fresh = PitcherWorkloadMetrics(
            "p1", "Rested Ace", pitches_7d=90, pitches_28d=360, velo_delta_mph=0.2
        )
        overused = PitcherWorkloadMetrics(
            "p2",
            "Overworked Starter",
            pitches_7d=130,
            pitches_28d=300,
            velo_delta_mph=-1.6,
            release_drop_in=-1.8,
        )
        r_fresh = engine.evaluate_fatigue(fresh)
        r_over = engine.evaluate_fatigue(overused)

        if (
            r_fresh.fatigue_tier == "OPTIMAL_FITNESS"
            and r_over.fatigue_tier == "HIGH_FATIGUE_OVERLOAD"
        ):
            checks.append(
                Check(
                    "pitcher fatigue engine",
                    True,
                    f"Fatigue verified (FRI: {r_over.fatigue_risk_index:.1f})",
                )
            )
        else:
            checks.append(
                Check(
                    "pitcher fatigue engine",
                    False,
                    f"Unexpected fatigue output: {r_fresh}, {r_over}",
                )
            )
    except Exception as exc:
        checks.append(Check("pitcher fatigue engine", False, str(exc)))
    return checks
