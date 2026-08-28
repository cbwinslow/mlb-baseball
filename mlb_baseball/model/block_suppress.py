"""Catcher Wild Pitch & Dirt Ball Wall Suppression Engine (BLOCK-SUPPRESS-01, ADR-217).

Provides dirt-ball blocking, recovery duration, and wild pitch advancement suppression:
1. Dirt Ball Wall Rating (DBWR score measuring block rate and recovery quickness).
2. Block-Advance Prevention Runs (BAPR net runs saved from runner advancement prevention).
3. Blocking Archetypes (Brick Wall Specialist, Leaky Dirt Liability, Slow Recovery).

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class CatcherDirtBlockMetrics:
    """Observed catcher dirt-ball blocking percentage, recovery time, and advancement prevention."""

    catcher_id: str
    catcher_name: str
    dirt_ball_block_pct: float = 89.0  # Spiked pitches blocked in front (benchmark ~88.0%)
    recovery_time_sec: float = 0.82  # Seconds to secure blocked ball (benchmark ~0.85s)
    runner_advance_prevention_pct: float = (
        78.0  # Fraction of dirt balls with 0 advances (benchmark ~75.0%)
    )
    dirt_ball_opportunities: int = 150


@dataclasses.dataclass(frozen=True)
class BlockSuppressEvaluationResult:
    """Evaluated dirt-ball blocking performance, DBWR rating, and BAPR runs saved."""

    catcher_name: str
    dbwr_score: float  # Dirt Ball Wall Rating (0 to 160)
    bapr_runs_saved: float  # Block-Advance Prevention Runs
    blocking_tier: str  # e.g. "BRICK_WALL_DIRT_SPECIALIST", "LEAKY_DIRT_BALL_LIABILITY"
    is_brick_wall: bool


class BaseBlockSuppressEngine(Protocol):
    """Polymorphic protocol for catcher dirt block engines."""

    def evaluate_blocking(
        self,
        metrics: CatcherDirtBlockMetrics,
    ) -> BlockSuppressEvaluationResult:
        """Calculate DBWR score and BAPR defensive runs saved."""
        ...


class CatcherBlockSuppressEngine:
    """Calculates dirt-ball blocking efficiency and recovery speed (BLOCK-SUPPRESS-01)."""

    def evaluate_blocking(
        self,
        metrics: CatcherDirtBlockMetrics,
    ) -> BlockSuppressEvaluationResult:
        """Compute DBWR rating and defensive run savings."""
        # DBWR Score: benchmark 88.0% block, 0.85s recovery, 75.0% advance prevention
        block_bonus = (metrics.dirt_ball_block_pct - 88.0) * 3.5
        recov_bonus = (0.85 - metrics.recovery_time_sec) * 80.0
        prev_bonus = (metrics.runner_advance_prevention_pct - 75.0) * 1.2
        dbwr = round(max(0.0, 100.0 + block_bonus + recov_bonus + prev_bonus), 1)

        # BAPR Runs Saved
        opps = max(1, metrics.dirt_ball_opportunities)
        block_saving = ((metrics.dirt_ball_block_pct - 88.0) / 100.0) * opps * 0.32
        prev_saving = ((metrics.runner_advance_prevention_pct - 75.0) / 100.0) * opps * 0.18
        bapr = round(block_saving + prev_saving, 2)

        is_wall = (
            dbwr >= 118.0
            and metrics.dirt_ball_block_pct >= 93.0
            and metrics.recovery_time_sec <= 0.72
        )

        # Tiers
        if is_wall:
            tier = "BRICK_WALL_DIRT_SPECIALIST"
        elif metrics.dirt_ball_block_pct <= 82.0 or dbwr <= 85.0:
            tier = "LEAKY_DIRT_BALL_LIABILITY"
        elif metrics.recovery_time_sec >= 0.95:
            tier = "SLOW_RECOVERY_DEFENDER"
        else:
            tier = "AVERAGE_DIRT_BLOCKER"

        return BlockSuppressEvaluationResult(
            catcher_name=metrics.catcher_name,
            dbwr_score=dbwr,
            bapr_runs_saved=bapr,
            blocking_tier=tier,
            is_brick_wall=is_wall,
        )


def health_check() -> list[Check]:
    """Operational health check for Catcher Block Suppress Engine (BLOCK-SUPPRESS-01)."""
    checks: list[Check] = []
    try:
        engine = CatcherBlockSuppressEngine()
        wall = CatcherDirtBlockMetrics("c1", "Jose Trevino", 96.0, 0.65, 90.0, 170)
        leaky = CatcherDirtBlockMetrics("c2", "Leaky Blocker", 80.0, 0.98, 65.0, 130)

        r_wal = engine.evaluate_blocking(wall)
        r_lea = engine.evaluate_blocking(leaky)

        if (
            r_wal.blocking_tier == "BRICK_WALL_DIRT_SPECIALIST"
            and r_lea.blocking_tier == "LEAKY_DIRT_BALL_LIABILITY"
        ):
            checks.append(
                Check(
                    "block suppress engine",
                    True,
                    f"Block Suppress verified (Trevino DBWR: {r_wal.dbwr_score:.1f})",
                )
            )
        else:
            checks.append(
                Check(
                    "block suppress engine",
                    False,
                    f"Unexpected block suppress output: {r_wal}, {r_lea}",
                )
            )
    except Exception as exc:
        checks.append(Check("block suppress engine", False, str(exc)))
    return checks
