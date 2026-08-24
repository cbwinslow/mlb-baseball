"""Catcher Wild Pitch & Passed Ball Wall Blocking Engine (WALL-BLOCK-01, ADR-249).

Provides dirt ball block %, runner advance suppression, and CWBEI index:
1. Catcher Wall Blocking Efficiency Index (CWBEI score measuring pitch smothering).
2. Blocked Runs Saved Above Average (BRSAA net defensive runs saved from wild pitch prevention).
3. Blocking Archetypes (Brick Wall Dirt Ball Blocker, Ole Ole Dirt Ball Leak).

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class CatcherWallBlockMetrics:
    """Observed dirt pitch block %, runner advance suppression %, and passed ball rate."""

    catcher_id: str
    catcher_name: str
    dirt_pitch_block_pct: float = 82.0  # Smother % on dirt pitches (benchmark ~82.0%)
    runner_advance_suppress_pct: float = 86.0  # Zero advance on block % (benchmark ~86.0%)
    passed_ball_rate_per_1000: float = 3.5  # Passed ball rate per 1000 inn (benchmark ~3.5)
    dirt_pitches_with_runners: int = 120


@dataclasses.dataclass(frozen=True)
class WallBlockEvaluationResult:
    """Evaluated catcher wall blocking score, runs saved, and blocking tier."""

    catcher_name: str
    cwbei_score: float  # Catcher Wall Blocking Efficiency Index (0 to 160)
    brsaa_runs_saved: float  # Net defensive runs saved from dirt ball blocks
    blocking_tier: str  # e.g. "BRICK_WALL_DIRT_BALL_BLOCKER", "OLE_OLE_DIRT_BALL_LEAK_LIABILITY"
    is_brick_wall: bool


class BaseWallBlockEngine(Protocol):
    """Polymorphic protocol for catcher wall blocking engines."""

    def evaluate_wall_block(
        self,
        metrics: CatcherWallBlockMetrics,
    ) -> WallBlockEvaluationResult:
        """Calculate CWBEI rating, BRSAA runs, and blocking tier."""
        ...


class CatcherWallBlockEngine:
    """Calculates dirt ball smother rate, runner advance suppression, and CWBEI (WALL-BLOCK-01)."""

    def evaluate_wall_block(
        self,
        metrics: CatcherWallBlockMetrics,
    ) -> WallBlockEvaluationResult:
        """Compute CWBEI score and defensive runs saved."""
        # CWBEI Score: benchmark 82.0% block, 86.0% suppress, 3.5 PB/1000
        block_bonus = (metrics.dirt_pitch_block_pct - 82.0) * 2.2
        suppress_bonus = (metrics.runner_advance_suppress_pct - 86.0) * 1.6
        pb_saving = (3.5 - metrics.passed_ball_rate_per_1000) * 4.5
        cwbei = round(max(0.0, 100.0 + block_bonus + suppress_bonus + pb_saving), 1)

        # BRSAA Runs (~0.0036 runs per dirt pitch with runners per point above 100)
        opps = max(1, metrics.dirt_pitches_with_runners)
        runs = round((cwbei - 100.0) * (opps * 0.0036), 2)

        is_wall = (
            cwbei >= 116.0
            and metrics.dirt_pitch_block_pct >= 89.0
            and metrics.runner_advance_suppress_pct >= 92.0
        )

        # Tiers
        if is_wall:
            tier = "BRICK_WALL_DIRT_BALL_BLOCKER"
        elif metrics.dirt_pitch_block_pct <= 72.0 or metrics.runner_advance_suppress_pct <= 76.0:
            tier = "OLE_OLE_DIRT_BALL_LEAK_LIABILITY"
        elif metrics.dirt_pitch_block_pct >= 86.0:
            tier = "SOLID_DIRT_BALL_SMOTHERER"
        else:
            tier = "AVERAGE_CATCHER_BLOCKING"

        return WallBlockEvaluationResult(
            catcher_name=metrics.catcher_name,
            cwbei_score=cwbei,
            brsaa_runs_saved=runs,
            blocking_tier=tier,
            is_brick_wall=is_wall,
        )


def health_check() -> list[Check]:
    """Operational health check for Catcher Wall Block Engine (WALL-BLOCK-01)."""
    checks: list[Check] = []
    try:
        engine = CatcherWallBlockEngine()
        wall_c = CatcherWallBlockMetrics("c1", "Patrick Bailey", 94.0, 96.0, 1.0, 150)
        leak_c = CatcherWallBlockMetrics("c2", "Leaky Catcher", 68.0, 72.0, 6.0, 90)

        r_wal = engine.evaluate_wall_block(wall_c)
        r_lea = engine.evaluate_wall_block(leak_c)

        if (
            r_wal.blocking_tier == "BRICK_WALL_DIRT_BALL_BLOCKER"
            and r_lea.blocking_tier == "OLE_OLE_DIRT_BALL_LEAK_LIABILITY"
        ):
            checks.append(
                Check(
                    "wall block engine",
                    True,
                    f"Wall Block verified (Bailey CWBEI: {r_wal.cwbei_score:.1f})",
                )
            )
        else:
            checks.append(
                Check(
                    "wall block engine",
                    False,
                    f"Unexpected wall block output: {r_wal}, {r_lea}",
                )
            )
    except Exception as exc:
        checks.append(Check("wall block engine", False, str(exc)))
    return checks
