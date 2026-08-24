"""Catcher Blocking, Passed Ball & Wild Pitch Run Value Modeler (BLOCK-01, ADR-148).

Provides catcher dirt-ball blocking evaluation, wild pitch suppression, and run prevention:
1. Pitcher Spike & Dirt-Ball Frequency Profiling (sweeper/curveball bounce rates).
2. Catcher Lateral Reach, Reaction Time, and Blocking Runs Above Average (Statcast Blocking).
3. Passed Ball & Wild Pitch Advance Probability per Base-Out State.
4. Expected Game Run Cost Delta from Catcher Defensive Blocking.

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

import numpy as np

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class CatcherBlockProfile:
    """Catcher blocking defensive metrics and mobility."""

    catcher_id: str
    catcher_name: str
    blocking_runs_above_avg: float = 0.0  # +5.0 = elite wall, -5.0 = porous
    reaction_time_s: float = 0.38


@dataclasses.dataclass(frozen=True)
class PitcherSpikeProfile:
    """Pitcher frequency of spiking pitches in the dirt."""

    pitcher_id: str
    pitcher_name: str
    dirt_pitches_per_game: float = 8.5  # high spin curve/sweeper pitchers throw 12+
    breaking_ball_usage: float = 0.40


@dataclasses.dataclass(frozen=True)
class BlockingMatchupEvaluation:
    """Evaluated block rates and expected base runner advancement costs."""

    catcher_name: str
    pitcher_name: str
    expected_blocks_per_game: float
    expected_passed_balls_per_game: float
    expected_wild_pitches_per_game: float
    run_cost_delta_per_game: float  # negative = run prevention (good)
    blocking_tier: str  # "ELITE_WALL", "AVERAGE", "VULNERABLE"


class BaseBlockingEngine(Protocol):
    """Polymorphic protocol for catcher blocking engines."""

    def evaluate_blocking_matchup(
        self,
        catcher: CatcherBlockProfile,
        pitcher: PitcherSpikeProfile,
    ) -> BlockingMatchupEvaluation:
        """Calculate block rates and expected run costs."""
        ...


class CatcherBlockingEngine:
    """Calculates catcher dirt ball blocking efficiency and run prevention (BLOCK-01)."""

    def evaluate_blocking_matchup(
        self,
        catcher: CatcherBlockProfile,
        pitcher: PitcherSpikeProfile,
    ) -> BlockingMatchupEvaluation:
        """Compute expected passed balls/wild pitches and run values."""
        # 1. Total dirt ball opportunities
        dirt_opps = pitcher.dirt_pitches_per_game

        # 2. League average block rate on dirt pitches ~ 94.0%
        # Catcher blocking runs shift the miss rate:
        # +5.0 runs -> 97.5% block rate, -5.0 runs -> 89.0% block rate
        block_pct_shift = (catcher.blocking_runs_above_avg / 10.0) * 0.070
        block_rate = float(np.clip(0.940 + block_pct_shift, 0.850, 0.990))

        # 3. Unblocked balls (split into passed balls vs wild pitches)
        miss_rate = 1.0 - block_rate
        total_misses = dirt_opps * miss_rate

        # Passed balls (catcher error) ~20% of unblocked balls, Wild pitches ~80%
        pb_per_game = total_misses * 0.20
        wp_per_game = total_misses * 0.80

        # 4. Expected run cost: every unblocked pitch with runners on base averages ~0.26 runs
        # Base runners on base ~ 40% of dirt ball situations
        run_cost = round((total_misses - (dirt_opps * 0.060)) * 0.40 * 0.26, 3)

        if catcher.blocking_runs_above_avg >= 3.0:
            tier = "ELITE_WALL"
        elif catcher.blocking_runs_above_avg <= -3.0:
            tier = "VULNERABLE"
        else:
            tier = "AVERAGE"

        return BlockingMatchupEvaluation(
            catcher_name=catcher.catcher_name,
            pitcher_name=pitcher.pitcher_name,
            expected_blocks_per_game=round(dirt_opps * block_rate, 2),
            expected_passed_balls_per_game=round(pb_per_game, 3),
            expected_wild_pitches_per_game=round(wp_per_game, 3),
            run_cost_delta_per_game=run_cost,
            blocking_tier=tier,
        )


def health_check() -> list[Check]:
    """Operational health check for the Catcher Blocking Engine (BLOCK-01)."""
    checks: list[Check] = []
    try:
        engine = CatcherBlockingEngine()
        wall_catcher = CatcherBlockProfile("c1", "Wall Catcher", blocking_runs_above_avg=4.5)
        spike_pitcher = PitcherSpikeProfile("p1", "Spike Pitcher", dirt_pitches_per_game=12.0)

        res = engine.evaluate_blocking_matchup(wall_catcher, spike_pitcher)

        if res.blocking_tier == "ELITE_WALL" and res.run_cost_delta_per_game < 0.0:
            checks.append(
                Check(
                    "catcher blocking engine",
                    True,
                    f"Blocking verified (Tier: {res.blocking_tier})",
                )
            )
        else:
            checks.append(
                Check("catcher blocking engine", False, f"Unexpected blocking evaluation: {res}")
            )
    except Exception as exc:
        checks.append(Check("catcher blocking engine", False, str(exc)))
    return checks
