"""Unit tests for Batter Two-Strike Approach Shortening Engine (TWO-STRIKE-01, ADR-196)."""

from mlb_baseball.model.two_strike import (
    BatterTwoStrikeMetrics,
    TwoStrikeApproachEngine,
    health_check,
)


def test_contact_battler_classified_as_elite_two_strike_battler():
    """Verify strong whiff reduction and swing shortening yields ELITE_TWO_STRIKE_BATTLER."""
    engine = TwoStrikeApproachEngine()

    kwan = BatterTwoStrikeMetrics(
        batter_id="b1",
        batter_name="Steven Kwan Archetype",
        early_count_whiff_pct=19.0,
        two_strike_whiff_pct=10.0,
        early_count_swing_length_ft=6.9,
        two_strike_swing_length_ft=6.1,
        early_count_ev_mph=88.5,
        two_strike_ev_mph=86.0,
        two_strike_pa_count=230,
        two_strike_k_pct=21.0,
    )

    res = engine.evaluate_two_strike(kwan)

    assert res.whiff_reduction_pct > 8.0
    assert res.swing_shortened_ft > 0.70
    assert res.tsbe_score > 125.0
    assert res.surplus_runs > 10.0
    assert res.approach_tier == "ELITE_TWO_STRIKE_BATTLER"
    assert res.is_elite_battler is True


def test_uncompromising_slugger_triggers_vulnerable_tier():
    """Verify no swing adjustment and high 2-strike K% triggers VULNERABLE_LONG_SWING_PULLER."""
    engine = TwoStrikeApproachEngine()

    slugger = BatterTwoStrikeMetrics(
        batter_id="b2",
        batter_name="Long Swing Slugger",
        early_count_whiff_pct=34.0,
        two_strike_whiff_pct=33.5,
        early_count_swing_length_ft=7.9,
        two_strike_swing_length_ft=7.9,
        early_count_ev_mph=95.0,
        two_strike_ev_mph=94.5,
        two_strike_pa_count=210,
        two_strike_k_pct=49.0,
    )

    res = engine.evaluate_two_strike(slugger)

    assert res.swing_shortened_ft == 0.0
    assert res.surplus_runs < 0.0
    assert res.approach_tier == "VULNERABLE_LONG_SWING_PULLER"
    assert res.is_elite_battler is False


def test_two_strike_health_check():
    """Verify two-strike approach health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Two-strike verified" in checks[0].detail
