"""Unit tests for Outfielder Throwing Arm Accuracy Engine (ARM-ACCURACY-01, ADR-201)."""

from mlb_baseball.model.arm_accuracy import (
    OutfieldArmAccuracyEngine,
    OutfieldArmAccuracyMetrics,
    health_check,
)


def test_elite_sniper_arm_evaluates_properly():
    """Verify high velocity, high accuracy, and strong hold rate yields DREADED_SNIPER_ARM."""
    engine = OutfieldArmAccuracyEngine()

    sniper = OutfieldArmAccuracyMetrics(
        fielder_id="f1",
        fielder_name="Sniper Arm Right Fielder",
        position="RF",
        max_throw_velo_mph=99.0,
        on_target_throw_pct=82.0,
        outfield_assists=15,
        runner_hold_pct=72.0,
        erratic_overthrows=0,
        opportunities_count=170,
    )

    res = engine.evaluate_arm(sniper)

    assert res.asi_score > 125.0
    assert res.rfsv_runs_saved > 10.0
    assert res.arm_tier == "DREADED_SNIPER_ARM"
    assert res.is_dreaded_sniper is True


def test_erratic_cannon_triggers_wild_arm_tier():
    """Verify high velo but low accuracy triggers RAW_ERRATIC_CANNON."""
    engine = OutfieldArmAccuracyEngine()

    wild_arm = OutfieldArmAccuracyMetrics(
        fielder_id="f2",
        fielder_name="Wild Arm",
        position="CF",
        max_throw_velo_mph=97.5,
        on_target_throw_pct=49.0,
        outfield_assists=5,
        runner_hold_pct=48.0,
        erratic_overthrows=6,
        opportunities_count=140,
    )

    res = engine.evaluate_arm(wild_arm)

    assert res.arm_tier == "RAW_ERRATIC_CANNON"
    assert res.is_dreaded_sniper is False


def test_arm_accuracy_health_check():
    """Verify arm accuracy health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Arm accuracy verified" in checks[0].detail
