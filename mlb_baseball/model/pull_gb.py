"""Batter Pull-Side Groundball Defense & Infield Positioning Engine (PULL-GB-01, ADR-203).

Provides infield positioning depth, pull-side groundball trapping, and defensive run savings:
1. Pull Groundball Fraction (PullGB% of total groundballs).
2. Optimal Infield Shading Depth (recommended fielding distance in feet).
3. Groundball Trap Index (GBTI score measuring pull vulnerability).
4. Positioning Archetypes (Extreme Pull Shading, Neutral, Opposite Field Alert).

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class BatterPullGBMetrics:
    """Observed batter groundball directional spray and exit velocity metrics."""

    batter_id: str
    batter_name: str
    batter_side: str = "L"  # "L" or "R"
    groundball_rate_pct: float = 48.0
    pull_groundball_pct: float = 62.0  # League average ~48.0%
    oppo_groundball_pct: float = 16.0
    hard_pull_gb_pct: float = 38.0  # Fraction of pulled GBs >= 95 mph
    groundball_count: int = 120


@dataclasses.dataclass(frozen=True)
class PullGBEvaluationResult:
    """Evaluated positioning depth, GBTI score, and positioning run savings."""

    batter_name: str
    optimal_depth_ft: float  # Infield depth in feet
    gbti_score: float  # Groundball Trap Index (0 to 160)
    pdrs_runs_saved: float  # Positioning Defensive Run Savings
    positioning_tier: str  # e.g. "EXTREME_PULL_SHADING_REQUIRED", "STRAIGHT_UP_NEUTRAL"
    requires_extreme_shading: bool


class BasePullGBEngine(Protocol):
    """Polymorphic protocol for pull-side groundball positioning engines."""

    def evaluate_positioning(
        self,
        metrics: BatterPullGBMetrics,
    ) -> PullGBEvaluationResult:
        """Calculate optimal depth, GBTI, and PDRS runs."""
        ...


class InfieldPositioningGBEngine:
    """Calculates infield positioning depth and groundball run savings (PULL-GB-01)."""

    def evaluate_positioning(
        self,
        metrics: BatterPullGBMetrics,
    ) -> PullGBEvaluationResult:
        """Compute shading recommendations and defensive run prevention."""
        # Optimal Depth: benchmark 150.0 ft + depth push from hard-hit balls
        depth = 150.0 + (metrics.hard_pull_gb_pct - 35.0) * 0.55
        depth = round(max(135.0, min(165.0, depth)), 1)

        # GBTI Score: benchmark 48.0% PullGB, 42.0% GB, 35.0% HardPull
        pull_bonus = (metrics.pull_groundball_pct - 48.0) * 2.4
        gb_bonus = (metrics.groundball_rate_pct - 42.0) * 1.5
        hard_bonus = (metrics.hard_pull_gb_pct - 35.0) * 1.1
        gbti = round(max(0.0, 100.0 + pull_bonus + gb_bonus + hard_bonus), 1)

        # PDRS Runs Saved: optimal positioning converts pulled GB singles to outs (~0.26 runs)
        gbs = max(1, metrics.groundball_count)
        pull_surplus = (metrics.pull_groundball_pct - 45.0) / 100.0
        pdrs = round(pull_surplus * gbs * 0.26, 2)

        is_extreme = gbti >= 118.0 and metrics.pull_groundball_pct >= 64.0

        # Tiers
        if is_extreme:
            tier = "EXTREME_PULL_SHADING_REQUIRED"
        elif metrics.oppo_groundball_pct >= 28.0:
            tier = "OPPOSITE_FIELD_GB_ALERT"
        elif 42.0 <= metrics.pull_groundball_pct <= 52.0:
            tier = "STRAIGHT_UP_NEUTRAL_POSITIONING"
        else:
            tier = "MODERATE_PULL_SHADING"

        return PullGBEvaluationResult(
            batter_name=metrics.batter_name,
            optimal_depth_ft=depth,
            gbti_score=gbti,
            pdrs_runs_saved=pdrs,
            positioning_tier=tier,
            requires_extreme_shading=is_extreme,
        )


def health_check() -> list[Check]:
    """Operational health check for Infield Positioning GB Engine (PULL-GB-01)."""
    checks: list[Check] = []
    try:
        engine = InfieldPositioningGBEngine()
        pull_heavy = BatterPullGBMetrics("b1", "Kyle Schwarber", "L", 50.0, 72.0, 10.0, 48.0, 140)
        neutral_h = BatterPullGBMetrics("b2", "Neutral Hitter", "R", 44.0, 46.0, 24.0, 32.0, 110)

        r_pul = engine.evaluate_positioning(pull_heavy)
        r_neu = engine.evaluate_positioning(neutral_h)

        if (
            r_pul.positioning_tier == "EXTREME_PULL_SHADING_REQUIRED"
            and r_neu.positioning_tier == "STRAIGHT_UP_NEUTRAL_POSITIONING"
        ):
            checks.append(
                Check(
                    "pull gb engine",
                    True,
                    f"Pull GB verified (Schwarber GBTI: {r_pul.gbti_score:.1f})",
                )
            )
        else:
            checks.append(
                Check("pull gb engine", False, f"Unexpected pull GB output: {r_pul}, {r_neu}")
            )
    except Exception as exc:
        checks.append(Check("pull gb engine", False, str(exc)))
    return checks
