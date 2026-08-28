"""Outfielder First-Step Reaction & Burst Route Engine (ROUTE-BURST-01, ADR-213).

Provides Statcast outfield jump decomposition (Reaction + Burst + Route Efficiency):
1. First-Step Reaction Time (t_react in seconds from contact to positive vector).
2. Acceleration Burst Speed (v_burst in ft/s after 1.5 seconds of top-speed sprint).
3. Route Efficiency Percentage (straight-line geodesic distance over actual path).
4. Burst-Route Fielding Efficiency Index (BRFEI score & Outfield Jump Surplus Runs).
5. Range Archetypes (Elite Ballhawk, Raw Speed Inefficient Router, Reaction Liability).

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class OutfielderBurstRouteMetrics:
    """Observed outfielder jump reaction time, sprint burst, and route efficiency."""

    fielder_id: str
    fielder_name: str
    position: str = "CF"
    reaction_time_sec: float = 0.44  # Contact to first step (benchmark ~0.44s)
    burst_velocity_ft_s: float = 27.0  # Top sprint speed at 1.5s (benchmark ~27.0 ft/s)
    route_efficiency_pct: float = 93.0  # Geodesic / actual path (benchmark ~93.0%)
    opportunity_count: int = 120


@dataclasses.dataclass(frozen=True)
class RouteBurstEvaluationResult:
    """Evaluated outfield jump efficiency, BRFEI index, and defensive run savings."""

    fielder_name: str
    position: str
    brfei_score: float  # Burst-Route Fielding Efficiency Index (0 to 160)
    oaa_jump_runs_saved: float  # Net defensive runs saved from range jump surplus
    range_tier: str  # e.g. "ELITE_BALLHAWK_BURST_ENGINE", "SLOW_REACTION_LIABILITY"
    is_elite_ballhawk: bool


class BaseRouteBurstEngine(Protocol):
    """Polymorphic protocol for outfield route burst engines."""

    def evaluate_route_burst(
        self,
        metrics: OutfielderBurstRouteMetrics,
    ) -> RouteBurstEvaluationResult:
        """Calculate BRFEI score, OAA jump runs, and range tier."""
        ...


class OutfielderRouteBurstEngine:
    """Calculates outfield jump reaction, sprint burst, and route efficiency (ROUTE-BURST-01)."""

    def evaluate_route_burst(
        self,
        metrics: OutfielderBurstRouteMetrics,
    ) -> RouteBurstEvaluationResult:
        """Compute BRFEI score and defensive run value."""
        # BRFEI Score: benchmark 0.44s reaction, 27.0 ft/s burst, 93.0% route
        react_bonus = (0.44 - metrics.reaction_time_sec) * 120.0
        burst_bonus = (metrics.burst_velocity_ft_s - 27.0) * 4.5
        route_bonus = (metrics.route_efficiency_pct - 93.0) * 1.8
        brfei = round(max(0.0, 100.0 + react_bonus + burst_bonus + route_bonus), 1)

        # OAA Jump Runs Saved: ~0.0018 runs per point above 100 per opportunity
        opps = max(1, metrics.opportunity_count)
        runs = round((brfei - 100.0) * (opps * 0.0018), 2)

        is_ballhawk = (
            brfei >= 118.0
            and metrics.reaction_time_sec <= 0.38
            and metrics.route_efficiency_pct >= 95.0
        )

        # Tiers
        if is_ballhawk:
            tier = "ELITE_BALLHAWK_BURST_ENGINE"
        elif metrics.burst_velocity_ft_s >= 28.0 and metrics.route_efficiency_pct <= 89.0:
            tier = "RAW_SPEED_INEFFICIENT_ROUTER"
        elif metrics.reaction_time_sec >= 0.55 or brfei <= 85.0:
            tier = "SLOW_REACTION_RANGE_LIABILITY"
        else:
            tier = "AVERAGE_OUTFIELD_BURST"

        return RouteBurstEvaluationResult(
            fielder_name=metrics.fielder_name,
            position=metrics.position,
            brfei_score=brfei,
            oaa_jump_runs_saved=runs,
            range_tier=tier,
            is_elite_ballhawk=is_ballhawk,
        )


def health_check() -> list[Check]:
    """Operational health check for Outfielder Route Burst Engine (ROUTE-BURST-01)."""
    checks: list[Check] = []
    try:
        engine = OutfielderRouteBurstEngine()
        ballhawk = OutfielderBurstRouteMetrics("f1", "Kevin Kiermaier", "CF", 0.34, 29.2, 97.5, 140)
        poor_route = OutfielderBurstRouteMetrics("f2", "Poor Route CF", "CF", 0.44, 28.5, 87.0, 100)

        r_bal = engine.evaluate_route_burst(ballhawk)
        r_por = engine.evaluate_route_burst(poor_route)

        if (
            r_bal.range_tier == "ELITE_BALLHAWK_BURST_ENGINE"
            and r_por.range_tier == "RAW_SPEED_INEFFICIENT_ROUTER"
        ):
            checks.append(
                Check(
                    "route burst engine",
                    True,
                    f"Route Burst verified (Kiermaier BRFEI: {r_bal.brfei_score:.1f})",
                )
            )
        else:
            checks.append(
                Check(
                    "route burst engine", False, f"Unexpected route burst output: {r_bal}, {r_por}"
                )
            )
    except Exception as exc:
        checks.append(Check("route burst engine", False, str(exc)))
    return checks
