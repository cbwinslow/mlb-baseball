"""Batter Pull-Side Air Contact vs Warning Track Trap Engine (AIR-TRAP-01, ADR-227).

Provides pull flyball power translation, warning-track dead zone trap, and HR conversion modeling:
1. Pull-Air Conversion vs Dead-Zone Trap Rating (PACDTR score measuring fence clearance).
2. Trap-To-HR Deficit Runs (TTHRD runs lost on warning track flyouts).
3. Trap Archetypes (Elite Wall-Clearing Pull Crusher, Warning Track Trapped Victim).

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class BatterAirTrapMetrics:
    """Observed batter pull flyball rate, warning track trap rate, and wall clearance HR %."""

    batter_id: str
    batter_name: str
    pull_flyball_rate_pct: float = 32.0  # Pull % on flyballs (benchmark ~32.0%)
    warning_track_trap_pct: float = 22.0  # % of pull flyballs caught at track (benchmark ~22.0%)
    wall_clearance_hr_pct: float = 18.0  # % of pull flyballs clearing fence (benchmark ~18.0%)
    flyball_count: int = 120


@dataclasses.dataclass(frozen=True)
class AirTrapEvaluationResult:
    """Evaluated pull-air conversion score, deficit runs, and fence clearance tier."""

    batter_name: str
    pacdtr_score: float  # Pull-Air Conversion vs Dead-Zone Trap Rating (0 to 160)
    tthrd_runs_lost: float  # Net offensive run deficit from warning track flyouts
    trap_tier: str  # e.g. "ELITE_WALL_CLEARING_PULL_CRUSHER", "WARNING_TRACK_POWER_TRAPPED_VICTIM"
    is_elite_clearer: bool


class BaseAirTrapEngine(Protocol):
    """Polymorphic protocol for pull-air warning track trap engines."""

    def evaluate_air_trap(
        self,
        metrics: BatterAirTrapMetrics,
    ) -> AirTrapEvaluationResult:
        """Calculate PACDTR score, run deficit, and trap tier."""
        ...


class BatterAirTrapEngine:
    """Calculates pull flyball fence clearance, warning track trap, and PACDTR (AIR-TRAP-01)."""

    def evaluate_air_trap(
        self,
        metrics: BatterAirTrapMetrics,
    ) -> AirTrapEvaluationResult:
        """Compute PACDTR rating and run deficit from trapped flyballs."""
        # PACDTR Score: benchmark 18.0% clearance, 22.0% trap, 32.0% pull FB
        clear_bonus = (metrics.wall_clearance_hr_pct - 18.0) * 3.2
        trap_saving = (22.0 - metrics.warning_track_trap_pct) * 2.4
        pull_bonus = (metrics.pull_flyball_rate_pct - 32.0) * 0.8
        pacdtr = round(max(0.0, 100.0 + clear_bonus + trap_saving + pull_bonus), 1)

        # TTHRD Runs: excess warning track catches lost vs benchmark (~1.25 runs per HR missed)
        fbs = max(1, metrics.flyball_count)
        excess_trap = ((metrics.warning_track_trap_pct - 22.0) / 100.0) * fbs
        runs_lost = round(-excess_trap * 1.25, 2)

        is_clearer = (
            pacdtr >= 116.0
            and metrics.wall_clearance_hr_pct >= 24.0
            and metrics.warning_track_trap_pct <= 17.0
        )

        # Tiers
        if is_clearer:
            tier = "ELITE_WALL_CLEARING_PULL_CRUSHER"
        elif metrics.warning_track_trap_pct >= 29.0 and metrics.wall_clearance_hr_pct <= 13.0:
            tier = "WARNING_TRACK_POWER_TRAPPED_VICTIM"
        elif metrics.pull_flyball_rate_pct >= 40.0 and metrics.wall_clearance_hr_pct <= 14.0:
            tier = "UNDER_POWERED_PULL_AIR_TRAPPER"
        elif metrics.wall_clearance_hr_pct >= 22.0:
            tier = "SOLID_PULL_FLYBALL_CONVERTER"
        else:
            tier = "AVERAGE_PULL_AIR_CONVERSION"

        return AirTrapEvaluationResult(
            batter_name=metrics.batter_name,
            pacdtr_score=pacdtr,
            tthrd_runs_lost=runs_lost,
            trap_tier=tier,
            is_elite_clearer=is_clearer,
        )


def health_check() -> list[Check]:
    """Operational health check for Batter Air Trap Engine (AIR-TRAP-01)."""
    checks: list[Check] = []
    try:
        engine = BatterAirTrapEngine()
        crusher = BatterAirTrapMetrics("b1", "Kyle Schwarber", 44.0, 14.0, 30.0, 160)
        trapped = BatterAirTrapMetrics("b2", "Warning Track Power", 36.0, 32.0, 10.0, 110)

        r_cru = engine.evaluate_air_trap(crusher)
        r_tra = engine.evaluate_air_trap(trapped)

        if (
            r_cru.trap_tier == "ELITE_WALL_CLEARING_PULL_CRUSHER"
            and r_tra.trap_tier == "WARNING_TRACK_POWER_TRAPPED_VICTIM"
        ):
            checks.append(
                Check(
                    "air trap engine",
                    True,
                    f"Air Trap verified (Schwarber PACDTR: {r_cru.pacdtr_score:.1f})",
                )
            )
        else:
            checks.append(
                Check("air trap engine", False, f"Unexpected air trap output: {r_cru}, {r_tra}")
            )
    except Exception as exc:
        checks.append(Check("air trap engine", False, str(exc)))
    return checks
