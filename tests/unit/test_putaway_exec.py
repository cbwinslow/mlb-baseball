"""Unit tests for Pitcher Two-Strike Putaway Execution Engine (PUTAWAY-EXEC-01, ADR-212)."""

from mlb_baseball.model.putaway_exec import (
    PitcherPutawayExecutionEngine,
    PitcherPutawayExecutionMetrics,
    health_check,
)


def test_surgical_sniper_classified_properly():
    """Verify high chase and low heart mistakes yields SURGICAL_TWO_STRIKE_SNIPER."""
    engine = PitcherPutawayExecutionEngine()

    cole = PitcherPutawayExecutionMetrics(
        pitcher_id="p1",
        pitcher_name="Gerrit Cole Archetype",
        two_strike_shadow_pct=45.0,
        two_strike_chase_pct=38.0,
        two_strike_heart_pct=10.0,
        two_strike_waste_pct=7.0,
        two_strike_pitch_count=400,
    )

    res = engine.evaluate_putaway_execution(cole)

    assert res.tsper_score > 125.0
    assert res.ptsv_runs_saved > 25.0
    assert res.execution_tier == "SURGICAL_TWO_STRIKE_SNIPER"
    assert res.is_surgical_sniper is True


def test_dangerous_heart_mistake_triggers_mistake_tier():
    """Verify high middle-middle frequency triggers DANGEROUS_HEART_MISTAKE_PRONE."""
    engine = PitcherPutawayExecutionEngine()

    mistake_pitcher = PitcherPutawayExecutionMetrics(
        pitcher_id="p2",
        pitcher_name="Heart Groover",
        two_strike_shadow_pct=30.0,
        two_strike_chase_pct=20.0,
        two_strike_heart_pct=28.0,
        two_strike_waste_pct=22.0,
        two_strike_pitch_count=260,
    )

    res = engine.evaluate_putaway_execution(mistake_pitcher)

    assert res.execution_tier == "DANGEROUS_HEART_MISTAKE_PRONE"
    assert res.is_surgical_sniper is False


def test_putaway_exec_health_check():
    """Verify putaway exec health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Putaway Exec verified" in checks[0].detail
