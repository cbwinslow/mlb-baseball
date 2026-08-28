"""Defensive Outfield Arm Strength & Runner Hold Engine (ARM-01, ADR-168).

Provides Statcast throw kinematics, base advancement suppression, and arm run value modeling:
1. Statcast Arm Throw Velocity (mph) and Exchange Transfer Time Kinematics.
2. Throw Arrival Time and Extra-Base Runner Hold Probability (Hold%).
3. Outfield Arm Runs Saved (ARM_runs) per 162 Games.
4. Fielder Arm Tiers (Cannon Elite, Above Average, Average, Weak Arm Target).

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
import math
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class OutfielderArmMetrics:
    """Observed throw speed, exchange time, and defensive position."""

    fielder_id: str
    fielder_name: str
    position: str = "RF"  # "LF", "CF", "RF"
    arm_velocity_mph: float = 93.0
    exchange_time_s: float = 0.75
    opportunities_per_season: int = 70


@dataclasses.dataclass(frozen=True)
class ArmEvaluationResult:
    """Evaluated throw kinematics, hold rates, and seasonal arm runs saved."""

    fielder_name: str
    position: str
    arm_velocity_mph: float
    throw_arrival_time_s: float  # Time from catch to infielder glove at 220ft
    hold_rate_pct: float  # % of runners held from taking extra base
    arm_runs_saved_season: float  # Net run impact over baseline
    arm_tier: str  # "CANNON_ELITE", "ABOVE_AVERAGE", "AVERAGE", "WEAK_ARM_TARGET"


class BaseArmEngine(Protocol):
    """Polymorphic protocol for outfield arm strength engines."""

    def evaluate_arm(
        self,
        metrics: OutfielderArmMetrics,
        benchmark_dist_ft: float = 220.0,
    ) -> ArmEvaluationResult:
        """Calculate throw arrival time, hold percentage, and ARM runs."""
        ...


class OutfieldArmEngine:
    """Calculates outfield throw kinematics, runner hold rates, and ARM runs (ARM-01)."""

    def evaluate_arm(
        self,
        metrics: OutfielderArmMetrics,
        benchmark_dist_ft: float = 220.0,
    ) -> ArmEvaluationResult:
        """Compute flight dynamics at benchmark 220ft throw distance."""
        # 1. Throw flight time: velocity in ft/s with 8% aerodynamic decay
        v_fps = max(50.0, metrics.arm_velocity_mph * 1.4667 * 0.92)
        t_flight = benchmark_dist_ft / v_fps
        t_arrival = round(metrics.exchange_time_s + t_flight, 2)

        # 2. Runner Hold Probability on 1st-to-3rd / 2nd-to-Home advancement
        # Benchmark runner arrival at 3rd is ~ 2.45s from ball contact with outfielder
        z = (2.55 - t_arrival) * 8.0
        hold_pct = round(float(1.0 / (1.0 + math.exp(-z))) * 100.0, 1)

        # 3. ARM Runs Saved over 162 games:
        # League average hold rate is ~ 60.0%. Each extra hold prevents ~ 0.28 runs.
        delta_holds = ((hold_pct - 60.0) / 100.0) * metrics.opportunities_per_season
        arm_runs = round(delta_holds * 0.28, 2)

        # 4. Arm Tier Classification:
        # Tier is driven solely by arm_runs_saved_season, the computed run
        # value this module exists to report. arm_runs already folds in both
        # inputs -- throw velocity (via flight time) and exchange time -- so a
        # raw arm_velocity_mph co-condition adds nothing but disagreement:
        # the old `or` form let a hard thrower with a slow exchange (strongly
        # negative arm_runs) be tagged CANNON_ELITE off velocity alone, and
        # an `and` form does the opposite, dropping a catastrophic arm
        # (arm_runs ~ -12) to AVERAGE just because its velocity cleared 85.
        if arm_runs >= 4.5:
            tier = "CANNON_ELITE"
        elif arm_runs >= 1.5:
            tier = "ABOVE_AVERAGE"
        elif arm_runs <= -3.0:
            tier = "WEAK_ARM_TARGET"
        else:
            tier = "AVERAGE"

        return ArmEvaluationResult(
            fielder_name=metrics.fielder_name,
            position=metrics.position,
            arm_velocity_mph=metrics.arm_velocity_mph,
            throw_arrival_time_s=t_arrival,
            hold_rate_pct=hold_pct,
            arm_runs_saved_season=arm_runs,
            arm_tier=tier,
        )


def health_check() -> list[Check]:
    """Operational health check for the Outfield Arm Engine (ARM-01)."""
    checks: list[Check] = []
    try:
        engine = OutfieldArmEngine()
        cannon = OutfielderArmMetrics(
            "f1", "Cannon Arm RF", "RF", arm_velocity_mph=99.0, exchange_time_s=0.68
        )
        weak = OutfielderArmMetrics(
            "f2", "Weak Arm LF", "LF", arm_velocity_mph=83.0, exchange_time_s=0.90
        )

        r_cannon = engine.evaluate_arm(cannon)
        r_weak = engine.evaluate_arm(weak)

        if r_cannon.arm_tier == "CANNON_ELITE" and r_weak.arm_tier == "WEAK_ARM_TARGET":
            checks.append(
                Check(
                    "outfield arm engine",
                    True,
                    f"Arm verified (ARM: {r_cannon.arm_runs_saved_season:>+4.1f} runs)",
                )
            )
        else:
            checks.append(
                Check("outfield arm engine", False, f"Unexpected arm output: {r_cannon}, {r_weak}")
            )
    except Exception as exc:
        checks.append(Check("outfield arm engine", False, str(exc)))
    return checks
