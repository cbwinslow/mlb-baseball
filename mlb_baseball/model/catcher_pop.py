"""Catcher Block-to-Throw & Stolen Base Prevention Engine (CATCHER-POP-01, ADR-193).

Provides ball-in-the-dirt recovery, secondary pop time, and wild pitch prevention modeling:
1. Block-to-Throw Time (Recovery Time + Secondary Pop Time).
2. Runner Advancement Deterrence Probability (suppressing extra base advances on dirt balls).
3. Block-to-Throw Surplus Value (BTSV in net run prevention).
4. Backstop Archetypes (Wall and Cannon Backstop, Elite Dirt Blocker, Slow Recovery Liability).

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class CatcherPopAndBlockMetrics:
    """Observed catcher pop times, recovery times, and dirt-ball fielding outcomes."""

    catcher_id: str
    catcher_name: str
    clean_pop_time_s: float = 1.94
    block_recovery_time_s: float = 0.62
    dirt_throw_velo_mph: float = 83.5
    blocked_pitches_count: int = 60
    wild_pitches_prevented: int = 16
    dirt_caught_stealing: int = 3
    passed_balls: int = 1


@dataclasses.dataclass(frozen=True)
class CatcherPopEvaluationResult:
    """Evaluated block-to-throw duration, runner deterrence, and BTSV run savings."""

    catcher_name: str
    total_block_throw_time_s: float
    advancement_deterrence_pct: float
    btsv_runs_saved: float
    catcher_tier: str  # e.g. "WALL_AND_CANNON_BACKSTOP", "ELITE_DIRT_BALL_BLOCKER"
    is_elite_backstop: bool


class BaseCatcherPopEngine(Protocol):
    """Polymorphic protocol for catcher pop and block engines."""

    def evaluate_catcher(
        self,
        metrics: CatcherPopAndBlockMetrics,
    ) -> CatcherPopEvaluationResult:
        """Calculate block-to-throw time, deterrence, and BTSV."""
        ...


class CatcherPopAndBlockEngine:
    """Calculates secondary pop times, dirt ball recovery, and BTSV (CATCHER-POP-01)."""

    def evaluate_catcher(
        self,
        metrics: CatcherPopAndBlockMetrics,
    ) -> CatcherPopEvaluationResult:
        """Compute block-to-throw time and BTSV run savings."""
        tot_time = round(metrics.clean_pop_time_s + metrics.block_recovery_time_s, 2)

        # Runner Advancement Deterrence %: benchmark is 2.50 seconds
        det = max(0.0, 100.0 - ((tot_time - 2.30) / 0.50) * 45.0)
        det = round(min(100.0, det), 1)

        # BTSV Runs Saved: WP prevented = +0.28 runs, Dirt CS = +0.44 runs, PB = -0.35 runs
        btsv = round(
            metrics.wild_pitches_prevented * 0.28
            + metrics.dirt_caught_stealing * 0.44
            - metrics.passed_balls * 0.35,
            2,
        )

        is_elite = btsv >= 4.0 or (metrics.clean_pop_time_s <= 1.90 and btsv >= 2.5)

        # Tiers
        if is_elite and metrics.clean_pop_time_s <= 1.90:
            tier = "WALL_AND_CANNON_BACKSTOP"
        elif btsv >= 2.50:
            tier = "ELITE_DIRT_BALL_BLOCKER"
        elif btsv <= -1.00 or metrics.passed_balls >= 4:
            tier = "SLOW_RECOVERY_LIABILITY"
        else:
            tier = "AVERAGE_BACKSTOP"

        return CatcherPopEvaluationResult(
            catcher_name=metrics.catcher_name,
            total_block_throw_time_s=tot_time,
            advancement_deterrence_pct=det,
            btsv_runs_saved=btsv,
            catcher_tier=tier,
            is_elite_backstop=is_elite,
        )


def health_check() -> list[Check]:
    """Operational health check for Catcher Pop & Block Engine (CATCHER-POP-01)."""
    checks: list[Check] = []
    try:
        engine = CatcherPopAndBlockEngine()
        realmuto = CatcherPopAndBlockMetrics("c1", "J.T. Realmuto", 1.87, 0.58, 86.0, 75, 20, 5, 0)
        slow_c = CatcherPopAndBlockMetrics("c2", "Slow Catcher", 2.08, 0.85, 78.0, 40, 5, 0, 5)

        r_rea = engine.evaluate_catcher(realmuto)
        r_slo = engine.evaluate_catcher(slow_c)

        if (
            r_rea.catcher_tier == "WALL_AND_CANNON_BACKSTOP"
            and r_slo.catcher_tier == "SLOW_RECOVERY_LIABILITY"
        ):
            checks.append(
                Check(
                    "catcher pop engine",
                    True,
                    f"Catcher pop verified (Realmuto BTSV: {r_rea.btsv_runs_saved:>+4.2f})",
                )
            )
        else:
            checks.append(
                Check("catcher pop engine", False, f"Unexpected catcher pop: {r_rea}, {r_slo}")
            )
    except Exception as exc:
        checks.append(Check("catcher pop engine", False, str(exc)))
    return checks
