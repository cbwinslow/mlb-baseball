"""Unit tests for Batter Breaking Ball Chase Recognition Engine (CHASE-RECOG-01, ADR-247)."""

from mlb_baseball.model.chase_recog import (
    BatterChaseRecogEngine,
    BatterChaseRecogMetrics,
    ChaseRecogEvaluationResult,
    health_check,
)


def test_discipline_hawk_classified_properly():
    """Verify sub-18% chase and 82%+ take yields ELITE_BREAKING_BALL_DISCIPLINE_HAWK."""
    engine = BatterChaseRecogEngine()

    soto = BatterChaseRecogMetrics(
        batter_id="b1",
        batter_name="Juan Soto Archetype",
        breaking_ball_chase_pct=15.0,
        breaking_ball_take_correct_pct=85.0,
        breaking_ball_waste_whiff_pct=35.0,
        out_of_zone_breaking_pitches=350,
    )

    res: ChaseRecogEvaluationResult = engine.evaluate_chase_recog(soto)

    assert res.bbcri_score > 125.0
    assert res.cdra_runs_produced > 20.0
    assert res.recognition_tier == "ELITE_BREAKING_BALL_DISCIPLINE_HAWK"
    assert res.is_discipline_hawk is True


def test_slider_bait_triggers_liability_tier():
    """Verify high chase and low take triggers FREE_SWINGING_SLIDER_BAIT_LIABILITY."""
    engine = BatterChaseRecogEngine()

    bait = BatterChaseRecogMetrics(
        batter_id="b2",
        batter_name="Free Swinger",
        breaking_ball_chase_pct=48.0,
        breaking_ball_take_correct_pct=52.0,
        breaking_ball_waste_whiff_pct=70.0,
        out_of_zone_breaking_pitches=250,
    )

    res = engine.evaluate_chase_recog(bait)

    assert res.recognition_tier == "FREE_SWINGING_SLIDER_BAIT_LIABILITY"
    assert res.is_discipline_hawk is False


def test_chase_recog_health_check():
    """Verify chase recog health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Chase Recog verified" in checks[0].detail
