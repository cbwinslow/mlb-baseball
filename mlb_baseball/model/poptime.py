"""Catcher Pop Time & Caught Stealing Above Average Engine (POPTIME-01, ADR-173).

Provides Statcast catcher throwing physics, pop time, and runner elimination modeling:
1. Statcast Pop Time to 2nd Base (Exchange Time + Throw Flight Duration).
2. Caught Stealing Expectancy (CS%) based on Pitcher Delivery and Pop Time.
3. Caught Stealing Above Average (CSAA_runs) per Season.
4. Catcher Throwing Tiers (Elite Pop Time, Above Average, Average, Slow Release Liability).

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
import math
from typing import Protocol

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class CatcherPopTimeMetrics:
    """Observed pop time and throw kinematics for a catcher."""

    catcher_id: str
    catcher_name: str
    pop_time_s: float = 1.95  # Time to 2nd base in seconds
    exchange_time_s: float = 0.65
    arm_velocity_mph: float = 85.0
    attempts_faced: int = 65


@dataclasses.dataclass(frozen=True)
class PopTimeEvaluationResult:
    """Evaluated caught stealing rate and seasonal run prevention."""

    catcher_name: str
    pop_time_s: float
    arm_velocity_mph: float
    expected_cs_pct: float  # Expected caught stealing %
    csaa_runs_saved: float  # Caught Stealing Above Average runs
    catcher_tier: str  # "ELITE_POP_TIME", "ABOVE_AVERAGE", "AVERAGE", "SLOW_RELEASE_LIABILITY"


class BasePopTimeEngine(Protocol):
    """Polymorphic protocol for catcher pop time engines."""

    def evaluate_pop_time(
        self,
        metrics: CatcherPopTimeMetrics,
        benchmark_slide_time: float = 1.98,
    ) -> PopTimeEvaluationResult:
        """Calculate expected CS% and seasonal CSAA runs."""
        ...


CS_PCT_LEAGUE_AVG = 0.21  # Real league-average CS% is ~21% (see POPTIME-01 note below)

# POPTIME-01 fix: the sigmoid's neutral point (delta_t == 0, i.e. pop time
# exactly at the benchmark slide time) must map to the real league-average
# CS% (~21%), not 50%. A logistic sigmoid(k*delta_t + b) hits 50% only when
# the argument is 0, so an intercept-free sigmoid(delta_t * 12.0) was
# silently telling every league-average catcher they were a coinflip to
# throw out a runner. Solving sigmoid(b) = CS_PCT_LEAGUE_AVG for the
# intercept: b = ln(p / (1 - p)) = ln(0.21 / 0.79) ~= -1.325. The slope
# (12.0) is left unchanged -- it was never the bug, and across a realistic
# pop-time range (~1.7s-2.3s, giving delta_t roughly -0.32 to +0.28 against
# the 1.98s benchmark) it keeps exp_cs inside ~[0.6%, 88.4%], strictly
# increasing as pop time gets faster (delta_t bigger) -- the correct
# direction, since a faster catcher throws out more runners.
_POPTIME_SIGMOID_INTERCEPT = math.log(CS_PCT_LEAGUE_AVG / (1.0 - CS_PCT_LEAGUE_AVG))


class CatcherPopTimeEngine:
    """Calculates catcher throw kinetics, CS%, and CSAA run value (POPTIME-01)."""

    def evaluate_pop_time(
        self,
        metrics: CatcherPopTimeMetrics,
        benchmark_slide_time: float = 1.98,
    ) -> PopTimeEvaluationResult:
        """Compute expected CS% and CSAA runs saved."""
        # 1. Expected Caught Stealing % using logistic arrival model
        # Benchmark margin: (Runner remaining time 2.05s) - (Catcher Pop Time)
        delta_t = benchmark_slide_time - metrics.pop_time_s
        z = delta_t * 12.0 + _POPTIME_SIGMOID_INTERCEPT
        exp_cs = round(float(1.0 / (1.0 + math.exp(-z))) * 100.0, 1)

        # 2. Caught Stealing Above Average Runs:
        # League average CS% is ~ 21.0%. Net out value is ~ 0.22 runs per CS swing.
        csaa_runs = round(
            ((exp_cs - CS_PCT_LEAGUE_AVG * 100.0) / 100.0) * metrics.attempts_faced * 0.22, 2
        )

        # 3. Catcher Throwing Tier.
        # The ABOVE_AVERAGE pop-time cut is strict (< benchmark): a catcher
        # sitting exactly at the benchmark slide time computes league-average
        # CS% and ~zero CSAA, so it must read AVERAGE, not ABOVE_AVERAGE.
        if metrics.pop_time_s <= 1.89 or csaa_runs >= 3.0:
            tier = "ELITE_POP_TIME"
        elif metrics.pop_time_s < benchmark_slide_time or csaa_runs >= 1.0:
            tier = "ABOVE_AVERAGE"
        elif metrics.pop_time_s > 2.06 or csaa_runs <= -2.5:
            tier = "SLOW_RELEASE_LIABILITY"
        else:
            tier = "AVERAGE"

        return PopTimeEvaluationResult(
            catcher_name=metrics.catcher_name,
            pop_time_s=metrics.pop_time_s,
            arm_velocity_mph=metrics.arm_velocity_mph,
            expected_cs_pct=exp_cs,
            csaa_runs_saved=csaa_runs,
            catcher_tier=tier,
        )


def health_check() -> list[Check]:
    """Operational health check for Catcher Pop Time Engine (POPTIME-01)."""
    checks: list[Check] = []
    try:
        engine = CatcherPopTimeEngine()
        elite = CatcherPopTimeMetrics(
            "c1", "J.T. Realmuto Archetype", pop_time_s=1.85, arm_velocity_mph=88.5
        )
        slow = CatcherPopTimeMetrics(
            "c2", "Slow Pop Catcher", pop_time_s=2.12, arm_velocity_mph=79.0
        )

        r_eli = engine.evaluate_pop_time(elite)
        r_slo = engine.evaluate_pop_time(slow)

        if (
            r_eli.catcher_tier == "ELITE_POP_TIME"
            and r_slo.catcher_tier == "SLOW_RELEASE_LIABILITY"
        ):
            checks.append(
                Check(
                    "catcher pop time engine",
                    True,
                    f"Pop time verified (Pop: {r_eli.pop_time_s:.2f}s)",
                )
            )
        else:
            checks.append(
                Check(
                    "catcher pop time engine",
                    False,
                    f"Unexpected pop time output: {r_eli}, {r_slo}",
                )
            )
    except Exception as exc:
        checks.append(Check("catcher pop time engine", False, str(exc)))
    return checks
