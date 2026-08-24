"""Unit tests for Outfielder Throw Accuracy Engine (OUTFIELD-TARGET-01, ADR-245)."""

from mlb_baseball.model.outfield_target import (
    OutfieldTargetEngine,
    OutfieldTargetEvaluationResult,
    OutfieldTargetMetrics,
    health_check,
)


def test_cannon_sniper_classified_properly():
    """Verify 80%+ accuracy and 94+ mph velo yields LASER_ACCURATE_CANNON_SNIPER."""
    engine = OutfieldTargetEngine()

    acuna = OutfieldTargetMetrics(
        fielder_id="f1",
        fielder_name="Ronald Acuña Jr. Archetype",
        position="RF",
        throw_accuracy_pct=86.0,
        arm_strength_mph=98.0,
        assist_conversion_pct=85.0,
        competitive_throw_chances=60,
    )

    res: OutfieldTargetEvaluationResult = engine.evaluate_outfield_target(acuna)

    assert res.oltai_score > 125.0
    assert res.oarp_runs_prevented > 5.0
    assert res.target_tier == "LASER_ACCURATE_CANNON_SNIPER"
    assert res.is_cannon_sniper is True


def test_wild_arm_triggers_liability_tier():
    """Verify sub-50% accuracy triggers ERRATIC_WILD_HOSE_LIABILITY."""
    engine = OutfieldTargetEngine()

    wild = OutfieldTargetMetrics(
        fielder_id="f2",
        fielder_name="Wild Arm Fielder",
        position="LF",
        throw_accuracy_pct=42.0,
        arm_strength_mph=85.0,
        assist_conversion_pct=40.0,
        competitive_throw_chances=35,
    )

    res = engine.evaluate_outfield_target(wild)

    assert res.target_tier == "ERRATIC_WILD_HOSE_LIABILITY"
    assert res.is_cannon_sniper is False


def test_outfield_target_health_check():
    """Verify outfield target health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Outfield Target verified" in checks[0].detail
