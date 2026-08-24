"""Unit tests for Batter BABIP Luck Deficit Engine (BABIP-LUCK-01, ADR-179)."""

from mlb_baseball.model.babip import (
    BABIPRegressionEngine,
    BatterBABIPInputs,
    health_check,
)


def test_unlucky_slugger_classified_as_severe_positive_regression():
    """Verify high hard-hit rate with depressed actual BABIP yields positive regression."""
    engine = BABIPRegressionEngine()

    unlucky = BatterBABIPInputs(
        batter_id="b1",
        batter_name="Unlucky Hard Hitter",
        actual_babip=0.230,
        ld_pct=0.24,
        gb_pct=0.42,
        fb_pct=0.34,
        hard_hit_pct=0.49,
        sprint_speed_fps=28.8,
        iffb_pct=0.03,
    )

    res = engine.evaluate_babip(unlucky)

    assert res.expected_xbabip > 0.340
    assert res.babip_luck_delta < -0.080
    assert res.regression_tier == "SEVERE_POSITIVE_REGRESSION"
    assert res.is_buy_low_candidate is True


def test_lucky_blooper_classified_as_severe_negative_regression():
    """Verify low hard-hit rate and popups with inflated BABIP yields negative regression."""
    engine = BABIPRegressionEngine()

    lucky = BatterBABIPInputs(
        batter_id="b2",
        batter_name="Lucky Soft Striker",
        actual_babip=0.390,
        ld_pct=0.15,
        gb_pct=0.45,
        fb_pct=0.40,
        hard_hit_pct=0.25,
        sprint_speed_fps=25.2,
        iffb_pct=0.16,
    )

    res = engine.evaluate_babip(lucky)

    assert res.expected_xbabip < 0.310
    assert res.babip_luck_delta > 0.080
    assert res.regression_tier == "SEVERE_NEGATIVE_REGRESSION"
    assert res.is_buy_low_candidate is False


def test_babip_health_check():
    """Verify BABIP health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "BABIP verified" in checks[0].detail
