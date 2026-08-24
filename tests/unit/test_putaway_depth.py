"""Unit tests for Pitcher Putaway Whiff Escalation Engine (PUTAWAY-DEPTH-01, ADR-244)."""

from mlb_baseball.model.putaway_depth import (
    PitcherPutawayDepthEngine,
    PitcherPutawayDepthMetrics,
    PutawayDepthEvaluationResult,
    health_check,
)


def test_putaway_executioner_classified_properly():
    """Verify 15%+ whiff surge and 48%+ 2-strike whiff yields LETHAL_TWO_STRIKE_EXECUTIONER."""
    engine = PitcherPutawayDepthEngine()

    skubal = PitcherPutawayDepthMetrics(
        pitcher_id="p1",
        pitcher_name="Tarik Skubal Archetype",
        early_count_whiff_pct=32.0,
        two_strike_whiff_pct=52.0,
        two_strike_chase_pct=48.0,
        two_strike_secondaries_count=200,
    )

    res: PutawayDepthEvaluationResult = engine.evaluate_putaway_depth(skubal)

    assert res.pwei_score > 125.0
    assert res.whiff_delta_pct == 20.0
    assert res.tssaa_strikeouts > 15.0
    assert res.tssrv_runs_saved > 4.0
    assert res.putaway_tier == "LETHAL_TWO_STRIKE_EXECUTIONER"
    assert res.is_executioner is True


def test_blunt_pitcher_triggers_blunt_tier():
    """Verify sub-4% whiff delta triggers BLUNT_WEAPON_NO_ESCALATION."""
    engine = PitcherPutawayDepthEngine()

    blunt = PitcherPutawayDepthMetrics(
        pitcher_id="p2",
        pitcher_name="Flat Arsenal Pitcher",
        early_count_whiff_pct=26.0,
        two_strike_whiff_pct=28.0,
        two_strike_chase_pct=28.0,
        two_strike_secondaries_count=100,
    )

    res = engine.evaluate_putaway_depth(blunt)

    assert res.putaway_tier == "BLUNT_WEAPON_NO_ESCALATION"
    assert res.is_executioner is False


def test_putaway_depth_health_check():
    """Verify putaway depth health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Putaway Depth verified" in checks[0].detail
