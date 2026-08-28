"""Batter High-Fastball Top-of-Zone Whiff vs Elevate Engine (HIGH-HEAT-01, ADR-231).

Provides high-velocity four-seam elevation vulnerability, whiff avoidance, and run value:
1. High-Heat Elevation Vulnerability Index (HHEVI score measuring mastery vs high fastballs).
2. High-Fastball Production Runs (HFPR net runs produced vs elevated heat).
3. Heat Archetypes (Elite High Fastball Crusher, Top-Zone Elevation Vulnerable).

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class BatterHighHeatMetrics:
    """Observed batter top-of-zone fastball swing %, whiff %, and hard hit %."""

    batter_id: str
    batter_name: str
    high_fb_swing_rate_pct: float = 60.0  # Swing % on elevated fastballs (benchmark ~60.0%)
    high_fb_whiff_rate_pct: float = 26.0  # Whiff % on elevated fastballs (benchmark ~26.0%)
    high_fb_hard_hit_pct: float = 36.0  # Hard-hit % on high FB contact (benchmark ~36.0%)
    high_fb_opportunities: int = 200


@dataclasses.dataclass(frozen=True)
class HighHeatEvaluationResult:
    """Evaluated high fastball mastery score, production runs, and elevation tier."""

    batter_name: str
    hhevi_score: float  # High-Heat Elevation Vulnerability Index (0 to 160)
    hfpr_runs_produced: float  # Net offensive runs produced against high heat
    heat_tier: str  # e.g. "ELITE_HIGH_FASTBALL_CRUSHER", "TOP_ZONE_ELEVATION_VULNERABLE"
    is_elite_crusher: bool


class BaseHighHeatEngine(Protocol):
    """Polymorphic protocol for high-heat evaluation engines."""

    def evaluate_high_heat(
        self,
        metrics: BatterHighHeatMetrics,
    ) -> HighHeatEvaluationResult:
        """Calculate HHEVI score, HFPR runs, and heat tier."""
        ...


class BatterHighHeatEngine:
    """Calculates top-of-zone fastball whiff avoidance, damage, and HHEVI (HIGH-HEAT-01)."""

    def evaluate_high_heat(
        self,
        metrics: BatterHighHeatMetrics,
    ) -> HighHeatEvaluationResult:
        """Compute HHEVI rating and high-fastball offensive runs produced."""
        # HHEVI Score: benchmark 26.0% whiff, 36.0% hard hit, 60.0% swing
        whiff_saving = (26.0 - metrics.high_fb_whiff_rate_pct) * 2.5
        hard_bonus = (metrics.high_fb_hard_hit_pct - 36.0) * 1.8
        swing_bonus = (metrics.high_fb_swing_rate_pct - 60.0) * 0.6
        hhevi = round(max(0.0, 100.0 + whiff_saving + hard_bonus + swing_bonus), 1)

        # HFPR Runs (~0.0022 runs per high heat opp per point above 100)
        opps = max(1, metrics.high_fb_opportunities)
        runs = round((hhevi - 100.0) * (opps * 0.0022), 2)

        is_crusher = (
            hhevi >= 116.0
            and metrics.high_fb_whiff_rate_pct <= 17.0
            and metrics.high_fb_hard_hit_pct >= 45.0
        )

        # Tiers
        if is_crusher:
            tier = "ELITE_HIGH_FASTBALL_CRUSHER"
        elif metrics.high_fb_whiff_rate_pct >= 34.0 and metrics.high_fb_hard_hit_pct <= 27.0:
            tier = "TOP_ZONE_ELEVATION_VULNERABLE"
        elif metrics.high_fb_hard_hit_pct >= 42.0:
            tier = "SOLID_HIGH_HEAT_SLUGGER"
        else:
            tier = "AVERAGE_HIGH_HEAT_HITTER"

        return HighHeatEvaluationResult(
            batter_name=metrics.batter_name,
            hhevi_score=hhevi,
            hfpr_runs_produced=runs,
            heat_tier=tier,
            is_elite_crusher=is_crusher,
        )


def health_check() -> list[Check]:
    """Operational health check for Batter High Heat Engine (HIGH-HEAT-01)."""
    checks: list[Check] = []
    try:
        engine = BatterHighHeatEngine()
        crusher = BatterHighHeatMetrics("b1", "Freddie Freeman", 66.0, 13.0, 52.0, 240)
        vulnerable = BatterHighHeatMetrics("b2", "High Whiff Batter", 62.0, 37.0, 24.0, 180)

        r_cru = engine.evaluate_high_heat(crusher)
        r_vul = engine.evaluate_high_heat(vulnerable)

        if (
            r_cru.heat_tier == "ELITE_HIGH_FASTBALL_CRUSHER"
            and r_vul.heat_tier == "TOP_ZONE_ELEVATION_VULNERABLE"
        ):
            checks.append(
                Check(
                    "high heat engine",
                    True,
                    f"High Heat verified (Freeman HHEVI: {r_cru.hhevi_score:.1f})",
                )
            )
        else:
            checks.append(
                Check("high heat engine", False, f"Unexpected high heat output: {r_cru}, {r_vul}")
            )
    except Exception as exc:
        checks.append(Check("high heat engine", False, str(exc)))
    return checks
