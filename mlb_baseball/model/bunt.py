"""Infield Bunt Defense & Short Game Run Prevention Engine (BUNT-01, ADR-185).

Provides corner infielder charging kinematics, sacrifice defense, and short game modeling:
1. Lead Runner Elimination Rate (throwing out runner at 2nd/3rd base on bunts).
2. Bunt Defense Run Savings (Lead Runner Out +0.38 runs, Popup +0.28 runs, Hit Allowed -0.45 runs).
3. Corner Infielder (1B/3B) and Pitcher Bunt Suppression Ratings.
4. Defense Tiers (Elite Bunt Eraser, Aggressive Charger, Short Game Liability, Average).

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class InfieldBuntDefenseMetrics:
    """Observed short game and bunt defensive fielding outcomes."""

    fielder_id: str
    fielder_name: str
    position: str = "3B"  # "1B", "3B", "P", "C"
    lead_runner_outs: int = 3  # Force out at 2nd or 3rd base
    batter_outs_at_first: int = 12  # Routine out at 1st base
    bunt_popups_caught: int = 2
    bunt_hits_allowed: int = 1
    total_bunt_attempts: int = 18


@dataclasses.dataclass(frozen=True)
class BuntDefenseEvaluationResult:
    """Evaluated bunt defense run savings and short game classification."""

    fielder_name: str
    position: str
    total_bunt_runs_saved: float  # Net run savings over average sacrifice outcome
    lead_runner_kill_pct: float  # % of bunt attempts resulting in lead runner out
    defense_tier: (
        str  # "ELITE_BUNT_ERASER", "AGGRESSIVE_CHARGER", "SHORT_GAME_LIABILITY", "AVERAGE"
    )
    is_elite_bunt_defender: bool


class BaseBuntDefenseEngine(Protocol):
    """Polymorphic protocol for bunt defense engines."""

    def evaluate_bunt_defense(
        self,
        metrics: InfieldBuntDefenseMetrics,
    ) -> BuntDefenseEvaluationResult:
        """Calculate bunt runs saved and defense tier."""
        ...


class InfieldBuntDefenseEngine:
    """Calculates short game run prevention and lead runner elimination (BUNT-01)."""

    def evaluate_bunt_defense(
        self,
        metrics: InfieldBuntDefenseMetrics,
    ) -> BuntDefenseEvaluationResult:
        """Compute net bunt runs saved and defense classification."""
        # 1. Net Bunt Runs Saved:
        # Lead runner out = +0.38 runs, Popup = +0.28 runs, Bunt hit allowed = -0.45 runs
        runs = round(
            metrics.lead_runner_outs * 0.38
            + metrics.bunt_popups_caught * 0.28
            - metrics.bunt_hits_allowed * 0.45,
            2,
        )

        # 2. Lead Runner Kill %
        tot = max(1, metrics.total_bunt_attempts)
        kill_pct = round((metrics.lead_runner_outs / tot) * 100.0, 1)

        # 3. Elite Bunt Defender Flag
        is_elite = runs >= 1.60 or metrics.lead_runner_outs >= 3

        # 4. Defense Tier
        if is_elite:
            tier = "ELITE_BUNT_ERASER"
        elif runs >= 0.70:
            tier = "AGGRESSIVE_CHARGER"
        elif runs <= -0.80 or metrics.bunt_hits_allowed >= 3:
            tier = "SHORT_GAME_LIABILITY"
        else:
            tier = "AVERAGE"

        return BuntDefenseEvaluationResult(
            fielder_name=metrics.fielder_name,
            position=metrics.position,
            total_bunt_runs_saved=runs,
            lead_runner_kill_pct=kill_pct,
            defense_tier=tier,
            is_elite_bunt_defender=is_elite,
        )


def health_check() -> list[Check]:
    """Operational health check for Infield Bunt Defense Engine (BUNT-01)."""
    checks: list[Check] = []
    try:
        engine = InfieldBuntDefenseEngine()
        arenado = InfieldBuntDefenseMetrics(
            "f1", "Nolan Arenado Archetype", "3B", lead_runner_outs=4, bunt_popups_caught=2
        )
        slow_1b = InfieldBuntDefenseMetrics(
            "f2", "Slow First Baseman", "1B", lead_runner_outs=0, bunt_hits_allowed=3
        )

        r_are = engine.evaluate_bunt_defense(arenado)
        r_slo = engine.evaluate_bunt_defense(slow_1b)

        if (
            r_are.defense_tier == "ELITE_BUNT_ERASER"
            and r_slo.defense_tier == "SHORT_GAME_LIABILITY"
        ):
            checks.append(
                Check(
                    "bunt defense engine",
                    True,
                    f"Bunt defense verified (Arenado Runs: {r_are.total_bunt_runs_saved:>+4.2f})",
                )
            )
        else:
            checks.append(
                Check("bunt defense engine", False, f"Unexpected bunt output: {r_are}, {r_slo}")
            )
    except Exception as exc:
        checks.append(Check("bunt defense engine", False, str(exc)))
    return checks
