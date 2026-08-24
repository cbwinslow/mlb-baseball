"""Catcher Quick Exchange & Throw Directional Accuracy Engine (CATCH-XCHG-01, ADR-209).

Provides catch-to-release exchange duration, pop time decomposition, and throw accuracy modeling:
1. Total Pop Time Decomposition (exchange duration + throw flight duration).
2. Catcher Exchange Velocity Index (CEVI score measuring transfer speed and arm power).
3. Stolen Base Deterrence Surplus Runs (net runs saved by throwing out baserunners).
4. Catcher Archetypes (Lightning Quick Cannon, Slow Transfer Strong Arm, Transfer Liability).

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class CatcherExchangeMetrics:
    """Observed catcher transfer time, throw velocity, flight time, and tag accuracy."""

    catcher_id: str
    catcher_name: str
    exchange_time_sec: float = 0.68  # Glove to hand transfer time (seconds)
    throw_velocity_mph: float = 82.5
    throw_flight_time_sec: float = 1.30  # Ball flight duration to 2B (seconds)
    throw_accuracy_pct: float = 68.0  # Accuracy inside the tag corridor
    stolen_base_attempts_against: int = 70


@dataclasses.dataclass(frozen=True)
class CatcherExchangeEvaluationResult:
    """Evaluated total pop time, CEVI score, and stolen base deterrence run savings."""

    catcher_name: str
    total_pop_time_sec: float  # Total pop time: exchange + flight
    cevi_score: float  # Catcher Exchange Velocity Index (0 to 160)
    sbd_runs_saved: float  # Net defensive runs saved from stolen base prevention
    transfer_tier: str  # e.g. "LIGHTNING_QUICK_EXCHANGE_CANNON", "POOR_ARM_TRANSFER_LIABILITY"
    is_lightning_transfer: bool


class BaseCatcherExchangeEngine(Protocol):
    """Polymorphic protocol for catcher exchange engines."""

    def evaluate_exchange(
        self,
        metrics: CatcherExchangeMetrics,
    ) -> CatcherExchangeEvaluationResult:
        """Calculate pop time, CEVI score, and stolen base deterrence runs."""
        ...


class CatcherExchangeEngine:
    """Calculates catcher glove exchange duration, pop time, and run value (CATCH-XCHG-01)."""

    def evaluate_exchange(
        self,
        metrics: CatcherExchangeMetrics,
    ) -> CatcherExchangeEvaluationResult:
        """Compute pop time decomposition, CEVI index, and deterrence runs."""
        # Total Pop Time: exchange duration + throw flight duration
        total_pop = round(metrics.exchange_time_sec + metrics.throw_flight_time_sec, 3)

        # CEVI Score: benchmark is 0.70 s transfer, 81.5 mph, 65.0% accuracy
        xchg_bonus = (0.70 - metrics.exchange_time_sec) * 160.0
        velo_bonus = (metrics.throw_velocity_mph - 81.5) * 1.8
        acc_bonus = (metrics.throw_accuracy_pct - 65.0) * 0.9
        cevi = round(max(0.0, 100.0 + xchg_bonus + velo_bonus + acc_bonus), 1)

        # SBD Runs Saved
        atts = max(1, metrics.stolen_base_attempts_against)
        xchg_saving = (0.70 - metrics.exchange_time_sec) * atts * 1.10
        acc_saving = (metrics.throw_accuracy_pct - 65.0) / 100.0 * atts * 0.22
        sbd_runs = round(xchg_saving + acc_saving, 2)

        is_lightning = (
            metrics.exchange_time_sec <= 0.64
            and cevi >= 115.0
            and metrics.throw_velocity_mph >= 84.0
        )

        # Tiers
        if is_lightning:
            tier = "LIGHTNING_QUICK_EXCHANGE_CANNON"
        elif metrics.exchange_time_sec >= 0.74 and metrics.throw_velocity_mph >= 84.0:
            tier = "STRONG_ARM_SLOW_TRANSFER"
        elif metrics.exchange_time_sec >= 0.76 or cevi <= 85.0:
            tier = "POOR_ARM_TRANSFER_LIABILITY"
        else:
            tier = "AVERAGE_CATCHER_TRANSFER"

        return CatcherExchangeEvaluationResult(
            catcher_name=metrics.catcher_name,
            total_pop_time_sec=total_pop,
            cevi_score=cevi,
            sbd_runs_saved=sbd_runs,
            transfer_tier=tier,
            is_lightning_transfer=is_lightning,
        )


def health_check() -> list[Check]:
    """Operational health check for Catcher Exchange Engine (CATCH-XCHG-01)."""
    checks: list[Check] = []
    try:
        engine = CatcherExchangeEngine()
        lightning = CatcherExchangeMetrics("c1", "J.T. Realmuto", 0.61, 87.0, 1.25, 80.0, 75)
        slow_arm = CatcherExchangeMetrics("c2", "Slow Transfer Catcher", 0.76, 85.0, 1.34, 60.0, 60)

        r_lig = engine.evaluate_exchange(lightning)
        r_slo = engine.evaluate_exchange(slow_arm)

        if (
            r_lig.transfer_tier == "LIGHTNING_QUICK_EXCHANGE_CANNON"
            and r_slo.transfer_tier == "STRONG_ARM_SLOW_TRANSFER"
        ):
            checks.append(
                Check(
                    "catch xchg engine",
                    True,
                    f"Catch Xchg verified (Realmuto Pop: {r_lig.total_pop_time_sec:.3f}s)",
                )
            )
        else:
            checks.append(
                Check("catch xchg engine", False, f"Unexpected catch xchg output: {r_lig}, {r_slo}")
            )
    except Exception as exc:
        checks.append(Check("catch xchg engine", False, str(exc)))
    return checks
