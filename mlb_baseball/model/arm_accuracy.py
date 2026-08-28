"""Outfielder Throwing Arm Accuracy & Base-Runner Freeze Index (ARM-ACCURACY-01, ADR-201).

Provides outfield throw accuracy, runner kill rates, and extra-base deterrence modeling:
1. On-Target Throw Accuracy (fraction of throws delivered cleanly into tag window).
2. Arm Sniper Index (ASI score combining velocity, trajectory precision, and hold rate).
3. Runner Freeze Surplus Value (RFSV net runs saved by suppressing extra-base advances).
4. Outfield Arm Archetypes (Dreaded Sniper Arm, Raw Erratic Cannon, Narrow Range Weak Arm).

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class OutfieldArmAccuracyMetrics:
    """Observed outfield throwing velocity, on-target accuracy, and runner hold rates."""

    fielder_id: str
    fielder_name: str
    position: str = "RF"  # "RF", "CF", "LF"
    max_throw_velo_mph: float = 93.0
    on_target_throw_pct: float = 68.0  # League average ~65.0%
    outfield_assists: int = 8
    runner_hold_pct: float = 54.0  # League average ~50.0%
    erratic_overthrows: int = 1
    opportunities_count: int = 140


@dataclasses.dataclass(frozen=True)
class ArmAccuracyEvaluationResult:
    """Evaluated arm precision, ASI score, and runner freeze run savings."""

    fielder_name: str
    position: str
    asi_score: float  # Arm Sniper Index (0 to 160)
    rfsv_runs_saved: float  # Net runs saved over baseline
    arm_tier: str  # e.g. "DREADED_SNIPER_ARM", "RAW_ERRATIC_CANNON"
    is_dreaded_sniper: bool


class BaseArmAccuracyEngine(Protocol):
    """Polymorphic protocol for outfield arm accuracy engines."""

    def evaluate_arm(
        self,
        metrics: OutfieldArmAccuracyMetrics,
    ) -> ArmAccuracyEvaluationResult:
        """Calculate accuracy score, ASI, and RFSV runs."""
        ...


class OutfieldArmAccuracyEngine:
    """Calculates outfield arm precision, runner deterrence, and RFSV (ARM-ACCURACY-01)."""

    def evaluate_arm(
        self,
        metrics: OutfieldArmAccuracyMetrics,
    ) -> ArmAccuracyEvaluationResult:
        """Compute ASI index, arm tier, and RFSV runs saved."""
        # ASI Score: benchmark is 65.0% accuracy, 90.0 mph velo, 50.0% hold rate
        acc_bonus = (metrics.on_target_throw_pct - 65.0) * 2.2
        velo_bonus = (metrics.max_throw_velo_mph - 90.0) * 1.8
        hold_bonus = (metrics.runner_hold_pct - 50.0) * 1.4
        asi = round(max(0.0, 100.0 + acc_bonus + velo_bonus + hold_bonus), 1)

        # RFSV Runs Saved: holding an advancing runner is worth ~0.18 runs, assist ~0.44 runs
        opps = max(1, metrics.opportunities_count)
        hold_delta = (metrics.runner_hold_pct - 50.0) / 100.0
        rfsv = round(
            (hold_delta * opps * 0.18)
            + (metrics.outfield_assists * 0.44)
            - (metrics.erratic_overthrows * 0.35),
            2,
        )

        is_sniper = (
            asi >= 118.0
            and metrics.on_target_throw_pct >= 74.0
            and metrics.max_throw_velo_mph >= 93.0
        )

        # Tiers
        if is_sniper:
            tier = "DREADED_SNIPER_ARM"
        elif metrics.max_throw_velo_mph >= 95.0 and metrics.on_target_throw_pct <= 56.0:
            tier = "RAW_ERRATIC_CANNON"
        elif metrics.max_throw_velo_mph <= 85.0 and asi <= 86.0:
            tier = "NARROW_RANGE_WEAK_ARM"
        else:
            tier = "AVERAGE_OUTFIELD_ARM"

        return ArmAccuracyEvaluationResult(
            fielder_name=metrics.fielder_name,
            position=metrics.position,
            asi_score=asi,
            rfsv_runs_saved=rfsv,
            arm_tier=tier,
            is_dreaded_sniper=is_sniper,
        )


def health_check() -> list[Check]:
    """Operational health check for Outfield Arm Accuracy Engine (ARM-ACCURACY-01)."""
    checks: list[Check] = []
    try:
        engine = OutfieldArmAccuracyEngine()
        sniper = OutfieldArmAccuracyMetrics(
            "f1", "Right Field Sniper", "RF", 98.5, 82.0, 14, 68.0, 0, 160
        )
        erratic = OutfieldArmAccuracyMetrics(
            "f2", "Erratic Cannon", "LF", 97.0, 48.0, 4, 48.0, 5, 140
        )

        r_sni = engine.evaluate_arm(sniper)
        r_err = engine.evaluate_arm(erratic)

        if r_sni.arm_tier == "DREADED_SNIPER_ARM" and r_err.arm_tier == "RAW_ERRATIC_CANNON":
            checks.append(
                Check(
                    "arm accuracy engine",
                    True,
                    f"Arm accuracy verified (Sniper ASI: {r_sni.asi_score:.1f})",
                )
            )
        else:
            checks.append(
                Check("arm accuracy engine", False, f"Unexpected arm accuracy: {r_sni}, {r_err}")
            )
    except Exception as exc:
        checks.append(Check("arm accuracy engine", False, str(exc)))
    return checks
