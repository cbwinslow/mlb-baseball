"""Unit tests for Bullpen Leverage Engine (LEV-01, ADR-154)."""

from mlb_baseball.model.leverage import (
    BullpenLeverageEngine,
    RelieverLeverageProfile,
    health_check,
)


def test_lockdown_closer_has_low_volatility_and_high_save_rate():
    """Verify elite K-BB closer achieves LOCKDOWN_ELITE status with >90% save rate."""
    engine = BullpenLeverageEngine()

    diaz = RelieverLeverageProfile(
        reliever_id="r1",
        reliever_name="Edwin Diaz Archetype",
        k_pct=0.38,
        bb_pct=0.06,
        hr_per_9=0.60,
        high_leverage_wpa=2.40,
    )

    res = engine.evaluate_closer_reliability(diaz)

    assert res.is_lockdown_closer is True
    assert res.closer_tier == "LOCKDOWN_ELITE"
    assert res.volatility_index < 35.0
    assert res.expected_save_conversion_pct > 89.0


def test_cardiac_closer_has_high_volatility_and_lower_conversion():
    """Verify high walk, high home run reliever has elevated blown-save volatility."""
    engine = BullpenLeverageEngine()

    wild_closer = RelieverLeverageProfile(
        reliever_id="r2",
        reliever_name="Wild Closer Archetype",
        k_pct=0.21,
        bb_pct=0.15,
        hr_per_9=1.50,
        high_leverage_wpa=0.20,
    )

    res = engine.evaluate_closer_reliability(wild_closer)

    assert res.is_lockdown_closer is False
    assert res.closer_tier == "CARDIAC_HIGH_VOLATILITY"
    assert res.volatility_index > 65.0
    assert res.expected_save_conversion_pct < 85.0


def test_leverage_health_check():
    """Verify leverage health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Leverage verified" in checks[0].detail
