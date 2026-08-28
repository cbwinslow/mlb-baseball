"""Outfielder Throw Accuracy & Direct Line Target Engine (OUTFIELD-TARGET-01, ADR-245).

Provides outfield throw precision, arm velocity, and assist prevention modeling:
1. Outfield Laser Target Accuracy Index (OLTAI score measuring throw accuracy).
2. Outfield Assist Runs Prevented (OARP net defensive runs saved from runner kills).
3. Target Archetypes (Laser Accurate Cannon Sniper, Erratic Wild Hose Liability).

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class OutfieldTargetMetrics:
    """Observed outfield throw accuracy %, arm strength mph, and assist conversion %."""

    fielder_id: str
    fielder_name: str
    position: str = "RF"
    throw_accuracy_pct: float = 65.0  # Throws within 4ft of target (benchmark ~65.0%)
    arm_strength_mph: float = 88.0  # Max competitive throw velocity (benchmark ~88.0 mph)
    assist_conversion_pct: float = 60.0  # Advance kill / hold conversion % (benchmark ~60.0%)
    competitive_throw_chances: int = 40


@dataclasses.dataclass(frozen=True)
class OutfieldTargetEvaluationResult:
    """Evaluated outfield target accuracy score, runs prevented, and sniper tier."""

    fielder_name: str
    position: str
    oltai_score: float  # Outfield Laser Target Accuracy Index (0 to 160)
    oarp_runs_prevented: float  # Net defensive runs prevented from accurate throws
    target_tier: str  # e.g. "LASER_ACCURATE_CANNON_SNIPER", "ERRATIC_WILD_HOSE_LIABILITY"
    is_cannon_sniper: bool


class BaseOutfieldTargetEngine(Protocol):
    """Polymorphic protocol for outfield target accuracy engines."""

    def evaluate_outfield_target(
        self,
        metrics: OutfieldTargetMetrics,
    ) -> OutfieldTargetEvaluationResult:
        """Calculate OLTAI rating, OARP runs, and target tier."""
        ...


class OutfieldTargetEngine:
    """Calculates throw accuracy, assist conversion, arm velo, and OLTAI (OUTFIELD-TARGET-01)."""

    def evaluate_outfield_target(
        self,
        metrics: OutfieldTargetMetrics,
    ) -> OutfieldTargetEvaluationResult:
        """Compute OLTAI score and defensive runs prevented."""
        # OLTAI Score: benchmark 65.0% acc, 60.0% conv, 88.0 mph
        acc_bonus = (metrics.throw_accuracy_pct - 65.0) * 2.2
        conv_bonus = (metrics.assist_conversion_pct - 60.0) * 1.6
        velo_bonus = (metrics.arm_strength_mph - 88.0) * 1.4
        oltai = round(max(0.0, 100.0 + acc_bonus + conv_bonus + velo_bonus), 1)

        # OARP Runs (~0.0035 runs per chance per point above 100)
        chances = max(1, metrics.competitive_throw_chances)
        runs = round((oltai - 100.0) * (chances * 0.0035), 2)

        is_sniper = (
            oltai >= 116.0
            and metrics.throw_accuracy_pct >= 78.0
            and metrics.arm_strength_mph >= 93.0
        )

        # Tiers
        if is_sniper:
            tier = "LASER_ACCURATE_CANNON_SNIPER"
        elif metrics.throw_accuracy_pct <= 50.0 or metrics.assist_conversion_pct <= 48.0:
            tier = "ERRATIC_WILD_HOSE_LIABILITY"
        elif metrics.throw_accuracy_pct >= 72.0:
            tier = "SOLID_ON_TARGET_FIELDER"
        else:
            tier = "AVERAGE_OUTFIELD_ACCURACY"

        return OutfieldTargetEvaluationResult(
            fielder_name=metrics.fielder_name,
            position=metrics.position,
            oltai_score=oltai,
            oarp_runs_prevented=runs,
            target_tier=tier,
            is_cannon_sniper=is_sniper,
        )


def health_check() -> list[Check]:
    """Operational health check for Outfield Target Engine (OUTFIELD-TARGET-01)."""
    checks: list[Check] = []
    try:
        engine = OutfieldTargetEngine()
        sniper = OutfieldTargetMetrics("f1", "Ronald Acuña Jr.", "RF", 85.0, 97.0, 84.0, 50)
        wild = OutfieldTargetMetrics("f2", "Wild Arm OF", "LF", 45.0, 86.0, 44.0, 30)

        r_sni = engine.evaluate_outfield_target(sniper)
        r_wil = engine.evaluate_outfield_target(wild)

        if (
            r_sni.target_tier == "LASER_ACCURATE_CANNON_SNIPER"
            and r_wil.target_tier == "ERRATIC_WILD_HOSE_LIABILITY"
        ):
            checks.append(
                Check(
                    "outfield target engine",
                    True,
                    f"Outfield Target verified (Acuña OLTAI: {r_sni.oltai_score:.1f})",
                )
            )
        else:
            checks.append(
                Check(
                    "outfield target engine",
                    False,
                    f"Unexpected outfield target output: {r_sni}, {r_wil}",
                )
            )
    except Exception as exc:
        checks.append(Check("outfield target engine", False, str(exc)))
    return checks
