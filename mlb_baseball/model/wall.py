"""Outfield Wall Collision & HR Robbery Run Value Engine (WALL-01, ADR-177).

Provides warning track kinematics, home run robbery, and wall collision defense modeling:
1. Home Run Robberies above fence plane (1.65 runs saved per robbery).
2. Extra-Base Wall Collision Catches (0.75 runs saved per catch).
3. Failed Wall Crash Deceleration Penalty (turn double into triple/error).
4. Outfield Wall Tiers (Elite Wall Thief, Fearless Wall Crasher, Wall Timid Fielder).

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class OutfielderWallMetrics:
    """Observed warning track and wall collision defensive outcomes."""

    fielder_id: str
    fielder_name: str
    position: str = "CF"  # "LF", "CF", "RF"
    hr_robberies: int = 2
    extra_base_wall_catches: int = 6
    wall_crashes_unsuccessful: int = 1
    opportunities: int = 28


@dataclasses.dataclass(frozen=True)
class WallDefenseEvaluationResult:
    """Evaluated wall defense runs saved and defensive classification."""

    fielder_name: str
    position: str
    hr_robberies: int
    total_wall_runs_saved: float  # Net run impact over baseline
    wall_catch_success_pct: float  # % of wall opportunities successfully converted
    wall_defense_tier: (
        str  # "ELITE_WALL_THIEF", "FEARLESS_WALL_CRASHER", "WALL_TIMID_FIELDER", "AVERAGE"
    )


class BaseWallDefenseEngine(Protocol):
    """Polymorphic protocol for outfield wall defense engines."""

    def evaluate_wall_defense(
        self,
        metrics: OutfielderWallMetrics,
    ) -> WallDefenseEvaluationResult:
        """Calculate wall runs saved and defense tier."""
        ...


class OutfieldWallEngine:
    """Calculates outfield wall collision catches and HR robbery run value (WALL-01)."""

    def evaluate_wall_defense(
        self,
        metrics: OutfielderWallMetrics,
    ) -> WallDefenseEvaluationResult:
        """Compute net wall runs saved and success rate."""
        # 1. Total Wall Runs Saved:
        # HR robbery = +1.65 runs, Extra-base wall catch = +0.75 runs, Failed crash = -0.65 runs
        runs = round(
            metrics.hr_robberies * 1.65
            + metrics.extra_base_wall_catches * 0.75
            - metrics.wall_crashes_unsuccessful * 0.65,
            2,
        )

        # 2. Wall Catch Success %
        total_catches = metrics.hr_robberies + metrics.extra_base_wall_catches
        opps = max(1, metrics.opportunities)
        succ_pct = round((total_catches / opps) * 100.0, 1)

        # 3. Defense Tier
        if runs >= 5.0 or metrics.hr_robberies >= 2:
            tier = "ELITE_WALL_THIEF"
        elif runs >= 2.2:
            tier = "FEARLESS_WALL_CRASHER"
        elif runs <= -1.2:
            tier = "WALL_TIMID_FIELDER"
        else:
            tier = "AVERAGE"

        return WallDefenseEvaluationResult(
            fielder_name=metrics.fielder_name,
            position=metrics.position,
            hr_robberies=metrics.hr_robberies,
            total_wall_runs_saved=runs,
            wall_catch_success_pct=succ_pct,
            wall_defense_tier=tier,
        )


def health_check() -> list[Check]:
    """Operational health check for Outfield Wall Defense Engine (WALL-01)."""
    checks: list[Check] = []
    try:
        engine = OutfieldWallEngine()
        thief = OutfielderWallMetrics(
            "f1", "Elite Center Fielder", "CF", hr_robberies=3, extra_base_wall_catches=5
        )
        timid = OutfielderWallMetrics(
            "f2",
            "Timid Left Fielder",
            "LF",
            hr_robberies=0,
            extra_base_wall_catches=1,
            wall_crashes_unsuccessful=3,
        )

        r_thi = engine.evaluate_wall_defense(thief)
        r_tim = engine.evaluate_wall_defense(timid)

        if (
            r_thi.wall_defense_tier == "ELITE_WALL_THIEF"
            and r_tim.wall_defense_tier == "WALL_TIMID_FIELDER"
        ):
            checks.append(
                Check(
                    "outfield wall engine",
                    True,
                    f"Wall defense verified (Thief: {r_thi.total_wall_runs_saved:>+4.1f} runs)",
                )
            )
        else:
            checks.append(
                Check("outfield wall engine", False, f"Unexpected wall output: {r_thi}, {r_tim}")
            )
    except Exception as exc:
        checks.append(Check("outfield wall engine", False, str(exc)))
    return checks
