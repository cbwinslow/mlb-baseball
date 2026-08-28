"""Unit tests for Infield Bunt Defense Charge & Barehand Engine (BUNT-CHARGE-01, ADR-233)."""

from mlb_baseball.model.bunt_charge import (
    BuntChargeEvaluationResult,
    InfieldBuntChargeEngine,
    InfieldBuntChargeMetrics,
    health_check,
)


def test_bunt_eraser_classified_properly():
    """Verify 90%+ conversion and sub-0.45s barehand yields ELITE_BAREHAND_BUNT_ERASER."""
    engine = InfieldBuntChargeEngine()

    chapman = InfieldBuntChargeMetrics(
        fielder_id="f1",
        fielder_name="Matt Chapman Archetype",
        position="3B",
        charge_sprint_speed_fps=28.2,
        barehand_transfer_sec=0.40,
        bunt_out_conversion_pct=92.0,
        bunt_chances_count=40,
    )

    res: BuntChargeEvaluationResult = engine.evaluate_bunt_charge(chapman)

    assert res.ibcdi_score > 125.0
    assert res.boaa_outs_saved > 6.0
    assert res.bcdrv_runs_saved > 2.5
    assert res.defense_tier == "ELITE_BAREHAND_BUNT_ERASER"
    assert res.is_elite_eraser is True


def test_slow_infielder_triggers_vulnerable_tier():
    """Verify sub-60% conversion and slow transfer triggers SLOW_FOOTWORK_BUNT_VULNERABLE."""
    engine = InfieldBuntChargeEngine()

    slow_3b = InfieldBuntChargeMetrics(
        fielder_id="f2",
        fielder_name="Slow 3B",
        position="3B",
        charge_sprint_speed_fps=21.5,
        barehand_transfer_sec=0.74,
        bunt_out_conversion_pct=56.0,
        bunt_chances_count=30,
    )

    res = engine.evaluate_bunt_charge(slow_3b)

    assert res.defense_tier == "SLOW_FOOTWORK_BUNT_VULNERABLE"
    assert res.is_elite_eraser is False


def test_bunt_charge_health_check():
    """Verify bunt charge health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Bunt Charge verified" in checks[0].detail
