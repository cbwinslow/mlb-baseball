"""Unit tests for Pitcher First-Pitch Strike Aggression Engine (FIRST-PITCH-AMBUSH-01, ADR-248)."""

from mlb_baseball.model.first_pitch_ambush import (
    FirstPitchAmbushEvaluationResult,
    PitcherFirstPitchAmbushEngine,
    PitcherFirstPitchAmbushMetrics,
    health_check,
)


def test_first_strike_commander_classified_properly():
    """Verify 68%+ F-Strike and low hard-hit yields SURGICAL_FIRST_STRIKE_COMMANDER."""
    engine = PitcherFirstPitchAmbushEngine()

    gilbert = PitcherFirstPitchAmbushMetrics(
        pitcher_id="p1",
        pitcher_name="Logan Gilbert Archetype",
        first_pitch_strike_pct=70.0,
        first_pitch_opponent_hard_hit_pct=30.0,
        first_pitch_opponent_slug_pct=0.340,
        total_batters_faced=240,
    )

    res: FirstPitchAmbushEvaluationResult = engine.evaluate_first_pitch_ambush(gilbert)

    assert res.fpcari_score > 125.0
    assert res.fplrs_runs_saved > 15.0
    assert res.ambush_tier == "SURGICAL_FIRST_STRIKE_COMMANDER"
    assert res.is_commander is True


def test_ambush_liability_triggers_liability_tier():
    """Verify low strike rate and high slugging triggers MEATBALL_AMBUSH_LIABILITY."""
    engine = PitcherFirstPitchAmbushEngine()

    meatball = PitcherFirstPitchAmbushMetrics(
        pitcher_id="p2",
        pitcher_name="First Pitch Groover",
        first_pitch_strike_pct=48.0,
        first_pitch_opponent_hard_hit_pct=58.0,
        first_pitch_opponent_slug_pct=0.660,
        total_batters_faced=160,
    )

    res = engine.evaluate_first_pitch_ambush(meatball)

    assert res.ambush_tier == "MEATBALL_AMBUSH_LIABILITY"
    assert res.is_commander is False


def test_first_pitch_ambush_health_check():
    """Verify first pitch ambush health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "First Pitch Ambush verified" in checks[0].detail
