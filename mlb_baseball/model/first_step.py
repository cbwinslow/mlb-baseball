"""Outfielder First-Step Reaction Burst & Jump Efficiency Engine (FIRST-STEP-01, ADR-237).

Provides initial reaction time, distance covered in first 1.5 seconds, and jump runs:
1. First-Step Reaction Jump Index (FSRJI score measuring initial burst efficiency).
2. Jump Runs Prevented (JRP net defensive runs saved by fast initial breaks).
3. Jump Archetypes (Elite Instinctive Ballhawk Burster, Hesitant Slow First Step Liability).

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class OutfielderFirstStepMetrics:
    """Observed outfielder reaction time sec, 1.5s distance ft, and jump efficiency %."""

    fielder_id: str
    fielder_name: str
    position: str = "CF"
    reaction_time_sec: float = 0.40  # Reaction time from sound of bat (benchmark ~0.40 s)
    distance_first_1_5s_ft: float = 32.0  # Distance in first 1.5s (benchmark ~32.0 ft)
    route_jump_efficiency_pct: float = 86.0  # Directional efficiency % (benchmark ~86.0%)
    outfield_flyball_chances: int = 120


@dataclasses.dataclass(frozen=True)
class FirstStepEvaluationResult:
    """Evaluated first step jump score, jump runs prevented, and burst tier."""

    fielder_name: str
    position: str
    fsrji_score: float  # First-Step Reaction Jump Index (0 to 160)
    jrp_runs_prevented: float  # Net defensive runs saved from quick breaks
    jump_tier: (
        str  # e.g. "ELITE_INSTINCTIVE_BALLHAWK_BURSTER", "HESITANT_SLOW_FIRST_STEP_LIABILITY"
    )
    is_elite_burster: bool


class BaseFirstStepEngine(Protocol):
    """Polymorphic protocol for outfielder first-step engines."""

    def evaluate_first_step(
        self,
        metrics: OutfielderFirstStepMetrics,
    ) -> FirstStepEvaluationResult:
        """Calculate FSRJI score, JRP runs, and jump tier."""
        ...


class OutfielderFirstStepEngine:
    """Calculates first-step reaction, initial burst distance, and FSRJI (FIRST-STEP-01)."""

    def evaluate_first_step(
        self,
        metrics: OutfielderFirstStepMetrics,
    ) -> FirstStepEvaluationResult:
        """Compute FSRJI rating and jump defensive runs prevented."""
        # FSRJI Score: benchmark 0.40 s reaction, 32.0 ft in 1.5s, 86.0% efficiency
        react_saving = (0.40 - metrics.reaction_time_sec) * 75.0
        dist_bonus = (metrics.distance_first_1_5s_ft - 32.0) * 3.2
        eff_bonus = (metrics.route_jump_efficiency_pct - 86.0) * 1.4
        fsrji = round(max(0.0, 100.0 + react_saving + dist_bonus + eff_bonus), 1)

        # JRP Runs (~0.0024 runs per outfield chance per point above 100)
        chances = max(1, metrics.outfield_flyball_chances)
        runs = round((fsrji - 100.0) * (chances * 0.0024), 2)

        is_burster = (
            fsrji >= 116.0
            and metrics.reaction_time_sec <= 0.32
            and metrics.distance_first_1_5s_ft >= 34.5
        )

        # Tiers
        if is_burster:
            tier = "ELITE_INSTINCTIVE_BALLHAWK_BURSTER"
        elif metrics.reaction_time_sec >= 0.52 or metrics.distance_first_1_5s_ft <= 28.5:
            tier = "HESITANT_SLOW_FIRST_STEP_LIABILITY"
        elif metrics.distance_first_1_5s_ft >= 33.5:
            tier = "SOLID_QUICK_JUMP_OUTFIELDER"
        else:
            tier = "AVERAGE_OUTFIELD_BURST"

        return FirstStepEvaluationResult(
            fielder_name=metrics.fielder_name,
            position=metrics.position,
            fsrji_score=fsrji,
            jrp_runs_prevented=runs,
            jump_tier=tier,
            is_elite_burster=is_burster,
        )


def health_check() -> list[Check]:
    """Operational health check for Outfielder First Step Engine (FIRST-STEP-01)."""
    checks: list[Check] = []
    try:
        engine = OutfielderFirstStepEngine()
        burster = OutfielderFirstStepMetrics("f1", "Kevin Kiermaier", "CF", 0.26, 37.0, 95.0, 150)
        hesitant = OutfielderFirstStepMetrics("f2", "Hesitant OF", "LF", 0.54, 28.0, 80.0, 100)

        r_bur = engine.evaluate_first_step(burster)
        r_hes = engine.evaluate_first_step(hesitant)

        if (
            r_bur.jump_tier == "ELITE_INSTINCTIVE_BALLHAWK_BURSTER"
            and r_hes.jump_tier == "HESITANT_SLOW_FIRST_STEP_LIABILITY"
        ):
            checks.append(
                Check(
                    "first step engine",
                    True,
                    f"First Step verified (Kiermaier FSRJI: {r_bur.fsrji_score:.1f})",
                )
            )
        else:
            checks.append(
                Check("first step engine", False, f"Unexpected first step output: {r_bur}, {r_hes}")
            )
    except Exception as exc:
        checks.append(Check("first step engine", False, str(exc)))
    return checks
