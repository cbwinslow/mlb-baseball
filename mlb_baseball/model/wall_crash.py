"""Outfielder Wall Crash Hazard & High-Impact Catch Engine (WALL-CRASH-01, ADR-221).

Provides warning-track wall proximity, collision fearlessness, and extra-base prevention:
1. Wall Crash Fearlessness Index (WCFI score measuring catch conversion at the barrier).
2. Wall Extra-Base Prevention Runs (WEBPR net defensive runs saved from wall catches).
3. Wall Hazard Archetypes (Fearless Wall Crash Defender, Timid Warning Track Pull Up).

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class OutfielderWallCrashMetrics:
    """Observed outfielder catch performance on flyballs landing within 4ft of the wall."""

    fielder_id: str
    fielder_name: str
    position: str = "CF"
    wall_hazard_catch_pct: float = 65.0  # Catch conversion at wall (benchmark ~65.0%)
    wall_collision_rate_pct: float = 30.0  # Fraction with body contact (benchmark ~30.0%)
    deceleration_cushion_ft: float = 4.6  # Stopping distance before wall (benchmark ~4.6 ft)
    wall_opportunities: int = 40


@dataclasses.dataclass(frozen=True)
class WallCrashEvaluationResult:
    """Evaluated wall catch fearlessness, surplus catches, and WEBPR runs saved."""

    fielder_name: str
    position: str
    wcfi_score: float  # Wall Crash Fearlessness Index (0 to 160)
    surplus_catches: float  # Extra warning track catches made above average
    webpr_runs_saved: float  # Net defensive runs saved by robbing extra-base hits
    hazard_tier: str  # e.g. "FEARLESS_WALL_CRASH_DEFENDER", "TIMID_WARNING_TRACK_PULL_UP"
    is_fearless_crasher: bool


class BaseWallCrashEngine(Protocol):
    """Polymorphic protocol for wall crash hazard engines."""

    def evaluate_wall_crash(
        self,
        metrics: OutfielderWallCrashMetrics,
    ) -> WallCrashEvaluationResult:
        """Calculate WCFI score, surplus catches, and WEBPR runs."""
        ...


class OutfielderWallCrashEngine:
    """Calculates wall proximity catch conversion and WEBPR runs (WALL-CRASH-01)."""

    def evaluate_wall_crash(
        self,
        metrics: OutfielderWallCrashMetrics,
    ) -> WallCrashEvaluationResult:
        """Compute WCFI fearlessness rating and extra-base prevention runs."""
        # WCFI Score: benchmark 65.0% catch, 30.0% collision, 4.6 ft cushion
        catch_bonus = (metrics.wall_hazard_catch_pct - 65.0) * 2.8
        collision_bonus = (metrics.wall_collision_rate_pct - 30.0) * 1.2
        cushion_bonus = (4.6 - metrics.deceleration_cushion_ft) * 12.0
        wcfi = round(max(0.0, 100.0 + catch_bonus + collision_bonus + cushion_bonus), 1)

        # Surplus Catches & WEBPR Runs Saved (~0.85 runs saved per robbed XBH)
        opps = max(1, metrics.wall_opportunities)
        surplus = round(((metrics.wall_hazard_catch_pct - 65.0) / 100.0) * opps, 2)
        surplus = max(0.0, surplus)
        webpr = round(surplus * 0.85, 2)

        is_fearless = (
            wcfi >= 118.0
            and metrics.wall_hazard_catch_pct >= 75.0
            and metrics.deceleration_cushion_ft <= 3.6
        )

        # Tiers
        if is_fearless:
            tier = "FEARLESS_WALL_CRASH_DEFENDER"
        elif metrics.wall_hazard_catch_pct <= 52.0 or metrics.deceleration_cushion_ft >= 6.0:
            tier = "TIMID_WARNING_TRACK_PULL_UP"
        elif metrics.wall_hazard_catch_pct >= 70.0:
            tier = "SOLID_WALL_COMMITTED_FIELDER"
        else:
            tier = "AVERAGE_WALL_APPROACH"

        return WallCrashEvaluationResult(
            fielder_name=metrics.fielder_name,
            position=metrics.position,
            wcfi_score=wcfi,
            surplus_catches=surplus,
            webpr_runs_saved=webpr,
            hazard_tier=tier,
            is_fearless_crasher=is_fearless,
        )


def health_check() -> list[Check]:
    """Operational health check for Outfielder Wall Crash Engine (WALL-CRASH-01)."""
    checks: list[Check] = []
    try:
        engine = OutfielderWallCrashEngine()
        fearless = OutfielderWallCrashMetrics(
            "f1", "Pete Crow-Armstrong", "CF", 82.0, 48.0, 2.9, 45
        )
        timid = OutfielderWallCrashMetrics("f2", "Timid Warning Track", "CF", 48.0, 15.0, 6.4, 35)

        r_fea = engine.evaluate_wall_crash(fearless)
        r_tim = engine.evaluate_wall_crash(timid)

        if (
            r_fea.hazard_tier == "FEARLESS_WALL_CRASH_DEFENDER"
            and r_tim.hazard_tier == "TIMID_WARNING_TRACK_PULL_UP"
        ):
            checks.append(
                Check(
                    "wall crash engine",
                    True,
                    f"Wall Crash verified (PCA WCFI: {r_fea.wcfi_score:.1f})",
                )
            )
        else:
            checks.append(
                Check("wall crash engine", False, f"Unexpected wall crash output: {r_fea}, {r_tim}")
            )
    except Exception as exc:
        checks.append(Check("wall crash engine", False, str(exc)))
    return checks
