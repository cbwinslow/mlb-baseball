"""Unit tests for Defensive Outfield Arm Strength Engine (ARM-01, ADR-168)."""

from mlb_baseball.model.arm import (
    OutfieldArmEngine,
    OutfielderArmMetrics,
    health_check,
)


def test_cannon_outfield_arm_classified_as_cannon_elite():
    """Verify 99 mph throw speed and quick transfer yields high hold rate and CANNON_ELITE."""
    engine = OutfieldArmEngine()

    cannon_rf = OutfielderArmMetrics(
        fielder_id="f1",
        fielder_name="Elite Arm RF",
        position="RF",
        arm_velocity_mph=99.5,
        exchange_time_s=0.65,
        opportunities_per_season=80,
    )

    res = engine.evaluate_arm(cannon_rf, benchmark_dist_ft=220.0)

    assert res.arm_tier == "CANNON_ELITE"
    assert res.hold_rate_pct > 75.0
    assert res.arm_runs_saved_season > 3.0
    assert res.throw_arrival_time_s < 2.40


def test_weak_outfield_arm_classified_as_weak_arm_target():
    """Verify slow throw speed yields low hold rate and negative ARM runs."""
    engine = OutfieldArmEngine()

    weak_lf = OutfielderArmMetrics(
        fielder_id="f2",
        fielder_name="Slow Arm LF",
        position="LF",
        arm_velocity_mph=82.0,
        exchange_time_s=0.92,
        opportunities_per_season=65,
    )

    res = engine.evaluate_arm(weak_lf, benchmark_dist_ft=220.0)

    assert res.arm_tier == "WEAK_ARM_TARGET"
    assert res.hold_rate_pct < 40.0
    assert res.arm_runs_saved_season < -3.0


def test_hard_thrower_with_slow_exchange_tagged_by_computed_run_value():
    """Regression (ADR-168): a 99 mph arm with a slow 1.5s exchange computes a
    strongly negative arm_runs_saved_season (~-11.6). The old `... or
    arm_velocity_mph >= 96.0` branch tagged it CANNON_ELITE off velocity alone;
    a naive `and` fix would instead drop it to AVERAGE. Tier is now driven by
    the computed run value alone, so this lands WEAK_ARM_TARGET.
    """
    engine = OutfieldArmEngine()
    hard_thrower_slow_exchange = OutfielderArmMetrics(
        fielder_id="f3",
        fielder_name="Cannon Slow Exchange",
        arm_velocity_mph=99.0,
        exchange_time_s=1.5,
    )

    res = engine.evaluate_arm(hard_thrower_slow_exchange)

    assert res.arm_runs_saved_season < -3.0
    assert res.arm_tier == "WEAK_ARM_TARGET"


def test_default_literal_metrics_tagged_average():
    """Regression (ADR-168): the dataclass's own literal defaults
    (arm_velocity_mph=93.0) compute an essentially neutral
    arm_runs_saved_season (~-0.02), but the old `... or arm_velocity_mph >=
    91.0` branch tagged it ABOVE_AVERAGE off velocity alone.
    """
    engine = OutfieldArmEngine()
    default_metrics = OutfielderArmMetrics(fielder_id="f4", fielder_name="Default Arm")

    res = engine.evaluate_arm(default_metrics)

    assert abs(res.arm_runs_saved_season) < 1.5
    assert res.arm_tier == "AVERAGE"


def test_arm_health_check():
    """Verify outfield arm health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Arm verified" in checks[0].detail
