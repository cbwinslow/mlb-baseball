"""Infield Bunt Defense Charging Speed & Barehand Conversion Engine (BUNT-CHARGE-01, ADR-233).

Provides infielder charge sprint speed, barehand scoop-to-throw time, and BOAA modeling:
1. Infield Bunt Charge Defense Index (IBCDI score measuring bunt erasure efficiency).
2. Bunt Outs Above Average (BOAA surplus outs recorded on sacrifice and drag bunts).
3. Defense Archetypes (Elite Barehand Bunt Eraser, Slow Footwork Bunt Vulnerable).

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class InfieldBuntChargeMetrics:
    """Observed infielder charge sprint speed fps, barehand transfer sec, and conversion %."""

    fielder_id: str
    fielder_name: str
    position: str = "3B"
    charge_sprint_speed_fps: float = 24.0  # Sprint speed charging bunt (benchmark ~24.0 ft/s)
    barehand_transfer_sec: float = 0.58  # Barehand scoop to release time (benchmark ~0.58 s)
    bunt_out_conversion_pct: float = 74.0  # Bunt out conversion % (benchmark ~74.0%)
    bunt_chances_count: int = 30


@dataclasses.dataclass(frozen=True)
class BuntChargeEvaluationResult:
    """Evaluated bunt charge defense score, BOAA outs saved, and defensive run value."""

    fielder_name: str
    position: str
    ibcdi_score: float  # Infield Bunt Charge Defense Index (0 to 160)
    boaa_outs_saved: float  # Bunt Outs Above Average
    bcdrv_runs_saved: float  # Net defensive runs saved from bunt defense
    defense_tier: str  # e.g. "ELITE_BAREHAND_BUNT_ERASER", "SLOW_FOOTWORK_BUNT_VULNERABLE"
    is_elite_eraser: bool


class BaseBuntChargeEngine(Protocol):
    """Polymorphic protocol for infield bunt charge defense engines."""

    def evaluate_bunt_charge(
        self,
        metrics: InfieldBuntChargeMetrics,
    ) -> BuntChargeEvaluationResult:
        """Calculate IBCDI rating, BOAA outs, and defensive runs."""
        ...


class InfieldBuntChargeEngine:
    """Calculates bunt charging speed, barehand scoop time, and IBCDI (BUNT-CHARGE-01)."""

    def evaluate_bunt_charge(
        self,
        metrics: InfieldBuntChargeMetrics,
    ) -> BuntChargeEvaluationResult:
        """Compute IBCDI score, BOAA outs saved, and defensive run value."""
        # IBCDI Score: benchmark 74.0% conv, 24.0 ft/s speed, 0.58 s barehand
        conv_bonus = (metrics.bunt_out_conversion_pct - 74.0) * 2.2
        speed_bonus = (metrics.charge_sprint_speed_fps - 24.0) * 3.0
        time_saving = (0.58 - metrics.barehand_transfer_sec) * 55.0
        ibcdi = round(max(0.0, 100.0 + conv_bonus + speed_bonus + time_saving), 1)

        # BOAA & BCDRV Runs Saved (~0.42 runs per bunt out secured)
        chances = max(1, metrics.bunt_chances_count)
        boaa = round(((metrics.bunt_out_conversion_pct - 74.0) / 100.0) * chances, 1)
        runs = round(boaa * 0.42, 2)

        is_eraser = (
            ibcdi >= 116.0
            and metrics.bunt_out_conversion_pct >= 84.0
            and metrics.barehand_transfer_sec <= 0.48
        )

        # Tiers
        if is_eraser:
            tier = "ELITE_BAREHAND_BUNT_ERASER"
        elif metrics.bunt_out_conversion_pct <= 62.0 or metrics.barehand_transfer_sec >= 0.70:
            tier = "SLOW_FOOTWORK_BUNT_VULNERABLE"
        elif metrics.bunt_out_conversion_pct >= 80.0:
            tier = "SOLID_BUNT_DEFENDER"
        else:
            tier = "AVERAGE_BUNT_DEFENDER"

        return BuntChargeEvaluationResult(
            fielder_name=metrics.fielder_name,
            position=metrics.position,
            ibcdi_score=ibcdi,
            boaa_outs_saved=boaa,
            bcdrv_runs_saved=runs,
            defense_tier=tier,
            is_elite_eraser=is_eraser,
        )


def health_check() -> list[Check]:
    """Operational health check for Infield Bunt Charge Engine (BUNT-CHARGE-01)."""
    checks: list[Check] = []
    try:
        engine = InfieldBuntChargeEngine()
        eraser = InfieldBuntChargeMetrics("f1", "Matt Chapman", "3B", 27.8, 0.42, 90.0, 35)
        slow = InfieldBuntChargeMetrics("f2", "Slow 3B", "3B", 22.0, 0.72, 58.0, 25)

        r_era = engine.evaluate_bunt_charge(eraser)
        r_slo = engine.evaluate_bunt_charge(slow)

        if (
            r_era.defense_tier == "ELITE_BAREHAND_BUNT_ERASER"
            and r_slo.defense_tier == "SLOW_FOOTWORK_BUNT_VULNERABLE"
        ):
            checks.append(
                Check(
                    "bunt charge engine",
                    True,
                    f"Bunt Charge verified (Chapman IBCDI: {r_era.ibcdi_score:.1f})",
                )
            )
        else:
            checks.append(
                Check(
                    "bunt charge engine", False, f"Unexpected bunt charge output: {r_era}, {r_slo}"
                )
            )
    except Exception as exc:
        checks.append(Check("bunt charge engine", False, str(exc)))
    return checks
