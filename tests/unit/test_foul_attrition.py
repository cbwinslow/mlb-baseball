"""Unit tests for Batter Two-Strike Foul Attrition Engine (FOUL-ATTRITION-01, ADR-216)."""

from mlb_baseball.model.foul_attrition import (
    BatterFoulAttritionEngine,
    BatterFoulAttritionMetrics,
    health_check,
)


def test_grinder_batter_classified_as_exhausting_grinder():
    """Verify high multi-foul PA% and 4.3+ P/PA yields EXHAUSTING_FOUL_BALL_GRINDER."""
    engine = BatterFoulAttritionEngine()

    nimmo = BatterFoulAttritionMetrics(
        batter_id="b1",
        batter_name="Brandon Nimmo Archetype",
        multi_foul_pa_rate_pct=20.0,
        pitches_per_pa=4.50,
        two_strike_foul_rate_pct=55.0,
        total_pa_count=600,
    )

    res = engine.evaluate_attrition(nimmo)

    assert res.bfai_score > 125.0
    assert res.surplus_pitches_extracted > 300.0
    assert res.srar_runs_saved > 10.0
    assert res.attrition_tier == "EXHAUSTING_FOUL_BALL_GRINDER"
    assert res.is_exhausting_grinder is True


def test_quick_hacker_triggers_rapid_dismissal_tier():
    """Verify low pitches per PA triggers RAPID_DISMISSAL_FREE_SWINGER."""
    engine = BatterFoulAttritionEngine()

    hacker = BatterFoulAttritionMetrics(
        batter_id="b2",
        batter_name="Free Swinger",
        multi_foul_pa_rate_pct=4.0,
        pitches_per_pa=3.30,
        two_strike_foul_rate_pct=28.0,
        total_pa_count=400,
    )

    res = engine.evaluate_attrition(hacker)

    assert res.attrition_tier == "RAPID_DISMISSAL_FREE_SWINGER"
    assert res.is_exhausting_grinder is False


def test_default_metrics_produce_neutral_bfai_score():
    """FOUL-ATTRITION-01 regression: the class's own defaults (multi_foul_pa_rate_pct=11.0,
    pitches_per_pa=3.95, two_strike_foul_rate_pct=42.0) are each documented as the
    benchmark in their own inline comments. Feeding the engine its own defaults should
    now produce an exactly neutral BFAI score of 100.0 and zero surplus pitches, instead
    of the positive drift the old unreconciled 10.0/3.90/40.0 anchors produced.
    """
    engine = BatterFoulAttritionEngine()
    default_batter = BatterFoulAttritionMetrics(batter_id="b3", batter_name="League Average")

    res = engine.evaluate_attrition(default_batter)

    assert res.bfai_score == 100.0
    assert res.surplus_pitches_extracted == 0.0
    assert res.srar_runs_saved == 0.0


def test_foul_attrition_health_check():
    """Verify foul attrition health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Foul Attrition verified" in checks[0].detail
