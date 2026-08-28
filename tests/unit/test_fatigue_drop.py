"""Unit tests for Pitcher Arm Fatigue Velocity Decay Engine (FATIGUE-DROP-01, ADR-236)."""

from mlb_baseball.model.fatigue_drop import (
    FatigueDropEvaluationResult,
    PitcherFatigueDropEngine,
    PitcherFatigueDropMetrics,
    health_check,
)


def test_workhorse_endurer_classified_properly():
    """Verify minimal velocity and release drop yields STEEL_ARM_WORKHORSE_ENDURER."""
    engine = PitcherFatigueDropEngine()

    wheeler = PitcherFatigueDropMetrics(
        pitcher_id="p1",
        pitcher_name="Zack Wheeler Archetype",
        late_game_velo_drop_mph=0.4,
        late_game_rel_drop_in=0.3,
        late_game_strike_pct=68.0,
        pitches_thrown_over_75=220,
    )

    res: FatigueDropEvaluationResult = engine.evaluate_fatigue_drop(wheeler)

    assert res.pafii_score > 125.0
    assert res.hfvrs_runs_saved > 15.0
    assert res.fatigue_tier == "STEEL_ARM_WORKHORSE_ENDURER"
    assert res.is_steel_arm_workhorse is True


def test_severe_fatigue_collapser_triggers_collapse_tier():
    """Verify 2.5+ mph velo drop and 3+ in release drop triggers SEVERE_FATIGUE_ARM_COLLAPSER."""
    engine = PitcherFatigueDropEngine()

    collapser = PitcherFatigueDropMetrics(
        pitcher_id="p2",
        pitcher_name="Collapsing Reliever",
        late_game_velo_drop_mph=2.8,
        late_game_rel_drop_in=3.4,
        late_game_strike_pct=52.0,
        pitches_thrown_over_75=140,
    )

    res = engine.evaluate_fatigue_drop(collapser)

    assert res.fatigue_tier == "SEVERE_FATIGUE_ARM_COLLAPSER"
    assert res.is_steel_arm_workhorse is False


def test_fatigue_drop_health_check():
    """Verify fatigue drop health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Fatigue Drop verified" in checks[0].detail
