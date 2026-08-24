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


def test_arm_health_check():
    """Verify outfield arm health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Arm verified" in checks[0].detail
