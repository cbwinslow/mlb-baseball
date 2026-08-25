"""Outfielder Wall Leap & Timing Elevation Engine (WALL-LEAP-01, ADR-253).

Provides vertical leap apex, timing precision error, and WLTEI index:
1. Wall Leap Timing & Elevation Index (WLTEI score measuring wall catch mastery).
2. Robbed Run Value Above Average (RRVAA net defensive runs saved from HR robberies).
3. Wall Leap Archetypes (Gravity Defying Wall Thief, Mistimed Ground Bound Liability).

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class OutfielderWallLeapMetrics:
    """Observed vertical leap apex, timing precision error, and above-wall catch %."""

    fielder_id: str
    fielder_name: str
    vertical_leap_apex_in: float = 18.0  # Vertical leap apex in inches (benchmark ~18.0 in)
    leap_timing_precision_ms: float = 95.0  # Timing error from apex in ms (benchmark ~95 ms)
    above_wall_catch_pct: float = 35.0  # Catch % on above-wall trajectories (benchmark ~35.0%)
    wall_leap_opportunities: int = 12


@dataclasses.dataclass(frozen=True)
class WallLeapEvaluationResult:
    """Evaluated wall leap score, robbed runs saved, and leap tier."""

    fielder_name: str
    wltei_score: float  # Wall Leap Timing & Elevation Index (0 to 160)
    rrvaa_runs_saved: float  # Net defensive runs saved from above-wall catches
    leap_tier: str  # e.g. "GRAVITY_DEFYING_WALL_THIEF", "GROUND_BOUND_MISTIMED_LEAP_LIABILITY"
    is_wall_thief: bool


class BaseWallLeapEngine(Protocol):
    """Polymorphic protocol for outfielder wall leap engines."""

    def evaluate_wall_leap(
        self,
        metrics: OutfielderWallLeapMetrics,
    ) -> WallLeapEvaluationResult:
        """Calculate WLTEI rating, RRVAA runs, and leap tier."""
        ...


class OutfielderWallLeapEngine:
    """Calculates wall leap height, timing synchronization, and WLTEI (WALL-LEAP-01)."""

    def evaluate_wall_leap(
        self,
        metrics: OutfielderWallLeapMetrics,
    ) -> WallLeapEvaluationResult:
        """Compute WLTEI score and robbed runs saved."""
        # WLTEI Score: benchmark 18.0 in apex, 95 ms timing error, 35.0% catch
        apex_bonus = (metrics.vertical_leap_apex_in - 18.0) * 1.8
        timing_bonus = (95.0 - metrics.leap_timing_precision_ms) * 0.6
        catch_bonus = (metrics.above_wall_catch_pct - 35.0) * 1.2
        wltei = round(max(0.0, 100.0 + apex_bonus + timing_bonus + catch_bonus), 1)

        # RRVAA Runs (~0.0085 runs per opportunity per point above 100)
        opps = max(1, metrics.wall_leap_opportunities)
        runs = round((wltei - 100.0) * (opps * 0.0085), 2)

        is_thief = (
            wltei >= 116.0
            and metrics.vertical_leap_apex_in >= 24.0
            and metrics.above_wall_catch_pct >= 55.0
        )

        # Tiers
        if is_thief:
            tier = "GRAVITY_DEFYING_WALL_THIEF"
        elif metrics.vertical_leap_apex_in <= 12.0 or metrics.above_wall_catch_pct <= 20.0:
            tier = "GROUND_BOUND_MISTIMED_LEAP_LIABILITY"
        elif metrics.vertical_leap_apex_in >= 20.0:
            tier = "SOLID_WALL_LEAP_FIELDER"
        else:
            tier = "AVERAGE_WALL_LEAP_FIELDER"

        return WallLeapEvaluationResult(
            fielder_name=metrics.fielder_name,
            wltei_score=wltei,
            rrvaa_runs_saved=runs,
            leap_tier=tier,
            is_wall_thief=is_thief,
        )


def health_check() -> list[Check]:
    """Operational health check for Outfielder Wall Leap Engine (WALL-LEAP-01)."""
    checks: list[Check] = []
    try:
        engine = OutfielderWallLeapEngine()
        thief = OutfielderWallLeapMetrics("f1", "Kevin Pillar", 30.0, 40.0, 68.0, 15)
        ground = OutfielderWallLeapMetrics("f2", "Ground Bound", 10.0, 140.0, 15.0, 8)

        r_thi = engine.evaluate_wall_leap(thief)
        r_gro = engine.evaluate_wall_leap(ground)

        if (
            r_thi.leap_tier == "GRAVITY_DEFYING_WALL_THIEF"
            and r_gro.leap_tier == "GROUND_BOUND_MISTIMED_LEAP_LIABILITY"
        ):
            checks.append(
                Check(
                    "wall leap engine",
                    True,
                    f"Wall Leap verified (Pillar WLTEI: {r_thi.wltei_score:.1f})",
                )
            )
        else:
            checks.append(
                Check(
                    "wall leap engine",
                    False,
                    f"Unexpected wall leap output: {r_thi}, {r_gro}",
                )
            )
    except Exception as exc:
        checks.append(Check("wall leap engine", False, str(exc)))
    return checks
