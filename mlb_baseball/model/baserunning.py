"""Dynamic Base Stealing & Pitcher Disengagement Physics Engine (SB-01, ADR-143).

Provides physical timing kinematics, pitcher disengagement tracking, and run expectancy modeling:
1. Physical Race Kinematics (Runner sprint speed & jump vs pitcher delivery & catcher pop-time).
2. Pitcher Disengagement Rules (0, 1, 2 step-offs, balk threshold & expanded secondary leads).
3. 24-State Base/Out Run Expectancy Breakeven Calculation.
4. Optimal Steal Green-Light Recommendation.

Adheres strictly to object-oriented encapsulation, polymorphic protocols, and
point-in-time correctness with zero lookahead leakage.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

import numpy as np

from mlb_baseball.health import Check


@dataclasses.dataclass(frozen=True)
class RunnerStealProfile:
    """Baserunner speed and acceleration profile."""

    runner_id: str
    runner_name: str
    sprint_speed_ft_s: float = 27.0  # MLB avg ~27.0 ft/s, elite > 29.5 ft/s
    base_lead_distance_ft: float = 10.5  # standard primary lead
    reaction_jump_time_s: float = 0.35  # time to break on first movement


@dataclasses.dataclass(frozen=True)
class PitcherDeliveryProfile:
    """Pitcher time to home plate and pickoff disengagement state."""

    pitcher_id: str
    pitcher_name: str
    delivery_time_s: float = 1.30  # slide step ~1.20s, high leg kick ~1.45s
    disengagements_used: int = 0  # 0, 1, or 2


@dataclasses.dataclass(frozen=True)
class CatcherArmProfile:
    """Catcher throw to 2nd base kinematics."""

    catcher_id: str
    catcher_name: str
    pop_time_s: float = 1.95  # elite < 1.85s, avg ~1.95s, poor > 2.05s
    arm_strength_mph: float = 84.0


@dataclasses.dataclass(frozen=True)
class StealSimulationResult:
    """Evaluated stolen base success probability and run expectancy value."""

    runner_name: str
    success_probability: float
    timing_margin_s: float  # positive = runner beats throw to bag
    runner_time_to_bag_s: float
    defense_time_to_bag_s: float
    breakeven_success_rate: float
    expected_run_value_delta: float
    is_green_light: bool


class BaseStealEngine(Protocol):
    """Polymorphic protocol for base stealing engines."""

    def evaluate_steal_attempt(
        self,
        runner: RunnerStealProfile,
        pitcher: PitcherDeliveryProfile,
        catcher: CatcherArmProfile,
        outs: int = 0,
        target_base: int = 2,
    ) -> StealSimulationResult:
        """Evaluate stolen base attempt physics and run expectancy."""
        ...


class BaseStealingPhysicsEngine:
    """Calculates physical race timing and run expectancy optimization for stolen bases (SB-01)."""

    def evaluate_steal_attempt(
        self,
        runner: RunnerStealProfile,
        pitcher: PitcherDeliveryProfile,
        catcher: CatcherArmProfile,
        outs: int = 0,
        target_base: int = 2,
    ) -> StealSimulationResult:
        """Calculate kinematic race to target base and breakeven run expectancy value."""
        # 1. Pitcher disengagement adjustments
        # After 2 disengagements, pitcher cannot step off again without balk risk:
        # Runner extends lead by +2.0 ft, reaction jump improves by 0.08s
        if pitcher.disengagements_used >= 2:
            effective_lead = runner.base_lead_distance_ft + 2.0
            effective_jump = max(0.20, runner.reaction_jump_time_s - 0.08)
        elif pitcher.disengagements_used == 1:
            effective_lead = runner.base_lead_distance_ft + 0.8
            effective_jump = runner.reaction_jump_time_s - 0.03
        else:
            effective_lead = runner.base_lead_distance_ft
            effective_jump = runner.reaction_jump_time_s

        # 2. Runner time to 2nd base (90 ft distance minus lead)
        distance_to_cover = 90.0 - effective_lead
        # Acceleration curve proxy: runner reaches top sprint speed after 15 ft
        accel_time_penalty = 0.25
        running_time = (distance_to_cover / runner.sprint_speed_ft_s) + accel_time_penalty
        total_runner_time = effective_jump + running_time

        # 3. Defensive time (pitcher delivery + catcher pop time + tag application)
        tag_time_s = 0.15  # time for infielder to receive ball and apply tag
        total_defense_time = pitcher.delivery_time_s + catcher.pop_time_s + tag_time_s

        # 4. Timing margin (positive = runner reaches bag before tag)
        margin_s = total_defense_time - total_runner_time

        # Logistic success probability curve: margin of 0s = ~50% success
        # margin of +0.20s = ~92% success, margin of -0.20s = ~8% success
        k_logistic = 11.5
        prob_success = float(1.0 / (1.0 + np.exp(-k_logistic * margin_s)))

        # 5. Run expectancy breakeven calculation
        # Run expectancy table approximations for 1st base steal:
        if outs == 0:
            re_current = 0.86
            re_success = 1.10  # runner on 2nd, 0 outs
            re_fail = 0.26  # empty, 1 out
        elif outs == 1:
            re_current = 0.51
            re_success = 0.66  # runner on 2nd, 1 out
            re_fail = 0.10  # empty, 2 outs
        else:  # 2 outs
            re_current = 0.22
            re_success = 0.32  # runner on 2nd, 2 outs
            re_fail = 0.00  # inning over

        re_gain = re_success - re_current
        re_loss = re_current - re_fail

        breakeven_p = re_loss / (re_gain + re_loss) if (re_gain + re_loss) > 0 else 0.75

        # Expected run value of the attempt: P(Success) * Gain - P(Fail) * Loss
        expected_run_delta = (prob_success * re_gain) - ((1.0 - prob_success) * re_loss)

        # Green light if expected run value is positive and success prob exceeds breakeven + buffer
        green_light = prob_success >= (breakeven_p + 0.03) and expected_run_delta > 0.01

        return StealSimulationResult(
            runner_name=runner.runner_name,
            success_probability=round(prob_success, 3),
            timing_margin_s=round(margin_s, 2),
            runner_time_to_bag_s=round(total_runner_time, 2),
            defense_time_to_bag_s=round(total_defense_time, 2),
            breakeven_success_rate=round(breakeven_p, 3),
            expected_run_value_delta=round(expected_run_delta, 3),
            is_green_light=green_light,
        )


def health_check() -> list[Check]:
    """Operational health check for the Base Stealing Physics Engine (SB-01)."""
    checks: list[Check] = []
    try:
        engine = BaseStealingPhysicsEngine()
        fast_runner = RunnerStealProfile("r1", "Speedy Runner", sprint_speed_ft_s=29.8)
        slow_pitcher = PitcherDeliveryProfile(
            "p1", "Slow Pitcher", delivery_time_s=1.40, disengagements_used=2
        )
        catcher = CatcherArmProfile("c1", "Avg Catcher", pop_time_s=1.95)

        res = engine.evaluate_steal_attempt(fast_runner, slow_pitcher, catcher, outs=1)

        if res.success_probability > 0.85 and res.is_green_light:
            checks.append(
                Check(
                    "base stealing physics engine",
                    True,
                    f"Steal kinematics verified (P(SB): {res.success_probability * 100:.1f}%)",
                )
            )
        else:
            checks.append(
                Check("base stealing physics engine", False, f"Unexpected steal simulation: {res}")
            )
    except Exception as exc:
        checks.append(Check("base stealing physics engine", False, str(exc)))
    return checks
