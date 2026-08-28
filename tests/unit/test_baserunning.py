"""Unit tests for Dynamic Base Stealing Physics Engine (SB-01, ADR-143)."""

from mlb_baseball.model.baserunning import (
    BaseStealingPhysicsEngine,
    CatcherArmProfile,
    PitcherDeliveryProfile,
    RunnerStealProfile,
    health_check,
)


def test_elite_runner_against_slow_delivery_and_disengagements():
    """Verify elite runner with 2 disengagements gets high win probability and green light."""
    engine = BaseStealingPhysicsEngine()

    runner = RunnerStealProfile(
        "r1", "Speedster", sprint_speed_ft_s=30.0, base_lead_distance_ft=11.0
    )
    pitcher = PitcherDeliveryProfile(
        "p1", "High Leg Kick", delivery_time_s=1.45, disengagements_used=2
    )
    catcher = CatcherArmProfile("c1", "Average Catcher", pop_time_s=1.95)

    res = engine.evaluate_steal_attempt(runner, pitcher, catcher, outs=0)

    assert res.success_probability > 0.88
    assert res.timing_margin_s > 0.15
    assert res.is_green_light is True
    assert res.expected_run_value_delta > 0.05


def test_slow_runner_against_quick_slide_step_gets_red_light():
    """Verify slow runner against quick slide-step pitcher gets red light."""
    engine = BaseStealingPhysicsEngine()

    slugger = RunnerStealProfile(
        "r2", "Slow Slugger", sprint_speed_ft_s=25.0, base_lead_distance_ft=9.0
    )
    pitcher = PitcherDeliveryProfile(
        "p2", "Slide Stepper", delivery_time_s=1.18, disengagements_used=0
    )
    catcher = CatcherArmProfile("c2", "Cannon Arm", pop_time_s=1.85)

    res = engine.evaluate_steal_attempt(slugger, pitcher, catcher, outs=1)

    assert res.success_probability < 0.35
    assert res.timing_margin_s < -0.20
    assert res.is_green_light is False
    assert res.expected_run_value_delta < 0.0


def test_baserunning_health_check():
    """Verify baserunning health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Steal kinematics verified" in checks[0].detail
