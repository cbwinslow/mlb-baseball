"""Batter Pull-Field Line-Drive Pull Slice Power Engine (PULL-SLICE-01, ADR-235).

Provides pull line-drive fairway conversion, foul-pole hook avoidance, and extra-base runs:
1. Pull Line-Drive Slice Rating (PLDSR score measuring fair line drive efficiency).
2. Fair-Pole Extra Base Runs (FPEBR offensive runs produced down the line).
3. Slice Archetypes (Elite Down The Line Pull Surgeon, Hooking Foul Ball Slicer).

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class BatterPullSliceMetrics:
    """Observed batter pull line drive %, fair pole conversion %, and hard hit %."""

    batter_id: str
    batter_name: str
    pull_ld_rate_pct: float = 18.0  # Pull line-drive % (benchmark ~18.0%)
    fair_pole_conversion_pct: float = 70.0  # Fair territory conversion % (benchmark ~70.0%)
    pull_ld_hard_hit_pct: float = 50.0  # Hard-hit % on pull line drives (benchmark ~50.0%)
    pull_ld_opportunities: int = 80


@dataclasses.dataclass(frozen=True)
class PullSliceEvaluationResult:
    """Evaluated pull line drive score, fair pole extra-base runs, and slice tier."""

    batter_name: str
    pldsr_score: float  # Pull Line-Drive Slice Rating (0 to 160)
    fpebr_runs_produced: float  # Net offensive runs produced from fair pull line drives
    slice_tier: str  # e.g. "ELITE_DOWN_THE_LINE_PULL_SURGEON", "HOOKING_FOUL_BALL_SLICER"
    is_elite_surgeon: bool


class BasePullSliceEngine(Protocol):
    """Polymorphic protocol for pull-slice evaluation engines."""

    def evaluate_pull_slice(
        self,
        metrics: BatterPullSliceMetrics,
    ) -> PullSliceEvaluationResult:
        """Calculate PLDSR rating, FPEBR runs, and slice tier."""
        ...


class BatterPullSliceEngine:
    """Calculates pull line-drive fair conversion, hook avoidance, and PLDSR (PULL-SLICE-01)."""

    def evaluate_pull_slice(
        self,
        metrics: BatterPullSliceMetrics,
    ) -> PullSliceEvaluationResult:
        """Compute PLDSR score and fair-pole extra-base runs produced."""
        # PLDSR Score: benchmark 70.0% fair conv, 18.0% pull LD, 50.0% hard hit
        conv_bonus = (metrics.fair_pole_conversion_pct - 70.0) * 2.0
        ld_bonus = (metrics.pull_ld_rate_pct - 18.0) * 1.8
        hard_bonus = (metrics.pull_ld_hard_hit_pct - 50.0) * 1.4
        pldsr = round(max(0.0, 100.0 + conv_bonus + ld_bonus + hard_bonus), 1)

        # FPEBR Runs (~0.0035 runs per pull LD opp per point above 100)
        opps = max(1, metrics.pull_ld_opportunities)
        runs = round((pldsr - 100.0) * (opps * 0.0035), 2)

        is_surgeon = (
            pldsr >= 116.0
            and metrics.fair_pole_conversion_pct >= 78.0
            and metrics.pull_ld_hard_hit_pct >= 58.0
        )

        # Tiers
        if is_surgeon:
            tier = "ELITE_DOWN_THE_LINE_PULL_SURGEON"
        elif metrics.fair_pole_conversion_pct <= 58.0:
            tier = "HOOKING_FOUL_BALL_SLICER"
        elif metrics.fair_pole_conversion_pct >= 75.0:
            tier = "SOLID_PULL_LINE_DRIVE_STRIKER"
        else:
            tier = "AVERAGE_PULL_LINE_DRIVE_HITTER"

        return PullSliceEvaluationResult(
            batter_name=metrics.batter_name,
            pldsr_score=pldsr,
            fpebr_runs_produced=runs,
            slice_tier=tier,
            is_elite_surgeon=is_surgeon,
        )


def health_check() -> list[Check]:
    """Operational health check for Batter Pull Slice Engine (PULL-SLICE-01)."""
    checks: list[Check] = []
    try:
        engine = BatterPullSliceEngine()
        surgeon = BatterPullSliceMetrics("b1", "Mookie Betts", 26.0, 84.0, 68.0, 95)
        hooker = BatterPullSliceMetrics("b2", "Hooking Batter", 20.0, 54.0, 48.0, 75)

        r_sur = engine.evaluate_pull_slice(surgeon)
        r_hoo = engine.evaluate_pull_slice(hooker)

        if (
            r_sur.slice_tier == "ELITE_DOWN_THE_LINE_PULL_SURGEON"
            and r_hoo.slice_tier == "HOOKING_FOUL_BALL_SLICER"
        ):
            checks.append(
                Check(
                    "pull slice engine",
                    True,
                    f"Pull Slice verified (Betts PLDSR: {r_sur.pldsr_score:.1f})",
                )
            )
        else:
            checks.append(
                Check("pull slice engine", False, f"Unexpected pull slice output: {r_sur}, {r_hoo}")
            )
    except Exception as exc:
        checks.append(Check("pull slice engine", False, str(exc)))
    return checks
