"""Unit tests for Pitcher Two-Strike Intent Leakage Engine (INTENT-LEAK-01, ADR-228)."""

from mlb_baseball.model.intent_leak import (
    IntentLeakEvaluationResult,
    PitcherIntentLeakEngine,
    PitcherPutawayIntentMetrics,
    health_check,
)


def test_command_sniper_classified_properly():
    """Verify sub-10% heart rate with high K% yields SURGICAL_PUTAWAY_COMMAND_SNIPER."""
    engine = PitcherIntentLeakEngine()

    burnes = PitcherPutawayIntentMetrics(
        pitcher_id="p1",
        pitcher_name="Corbin Burnes Archetype",
        chase_dirt_intent_pct=68.0,
        heart_zone_leak_pct=8.0,
        two_strike_k_pct=52.0,
        two_strike_pitches_count=520,
    )

    res: IntentLeakEvaluationResult = engine.evaluate_intent_leak(burnes)

    assert res.tspiei_score > 125.0
    assert res.hpcr_runs_prevented > 15.0
    assert res.intent_tier == "SURGICAL_PUTAWAY_COMMAND_SNIPER"
    assert res.is_surgical_sniper is True


def test_meatball_leaker_triggers_fatal_tier():
    """Verify 28%+ heart mistake rate triggers FATAL_TWO_STRIKE_MEATBALL_LEAKER."""
    engine = PitcherIntentLeakEngine()

    leaker = PitcherPutawayIntentMetrics(
        pitcher_id="p2",
        pitcher_name="Meatball Reliever",
        chase_dirt_intent_pct=40.0,
        heart_zone_leak_pct=30.0,
        two_strike_k_pct=24.0,
        two_strike_pitches_count=300,
    )

    res = engine.evaluate_intent_leak(leaker)

    assert res.hpcr_runs_prevented < -8.0
    assert res.intent_tier == "FATAL_TWO_STRIKE_MEATBALL_LEAKER"
    assert res.is_surgical_sniper is False


def test_intent_leak_health_check():
    """Verify intent leak health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Intent Leak verified" in checks[0].detail
