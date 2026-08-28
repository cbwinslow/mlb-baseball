"""Unit tests for Batter Contact-Type Expected Slugging Engine (XSLG-01, ADR-187)."""

from mlb_baseball.model.xslg import (
    BatterContactBins,
    XSLGPowerEngine,
    health_check,
)


def test_elite_barrel_slugger_evaluates_properly():
    """Verify high barrel counts yield high xSLG, xISO, and ELITE_BARREL_SLUGGER."""
    engine = XSLGPowerEngine()

    judge = BatterContactBins(
        batter_id="b1",
        batter_name="Aaron Judge Archetype",
        barrel_count=36,
        solid_contact_count=20,
        flare_burner_count=26,
        under_count=16,
        topped_count=28,
        weak_count=10,
        total_bbe=136,
        actual_iso=0.360,
    )

    res = engine.evaluate_power(judge)

    assert res.expected_xslg > 0.650
    assert res.expected_xiso > 0.280
    assert res.power_tier == "ELITE_BARREL_SLUGGER"
    assert res.is_elite_slugger is True


def test_undervalued_power_ceiling_triggers_for_unlucky_slugger():
    """Verify depressed actual ISO with high expected xISO yields UNDERVALUED_POWER_CEILING."""
    engine = XSLGPowerEngine()

    unlucky = BatterContactBins(
        batter_id="b2",
        batter_name="Unlucky Slugger",
        barrel_count=26,
        solid_contact_count=18,
        flare_burner_count=28,
        under_count=18,
        topped_count=30,
        weak_count=12,
        total_bbe=132,
        actual_iso=0.160,
    )

    res = engine.evaluate_power(unlucky)

    assert res.expected_xiso > 0.220
    assert res.tpce_efficiency_pct < 75.0
    assert res.power_tier == "UNDERVALUED_POWER_CEILING"
    assert res.is_elite_slugger is False


def test_xslg_health_check():
    """Verify xSLG health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "xSLG verified" in checks[0].detail
