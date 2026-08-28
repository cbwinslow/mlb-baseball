"""Unit tests for Defensive Outfield Catch Probability Engine (CATCH-PROB-01, ADR-189)."""

from mlb_baseball.model.catch_prob import (
    OutfieldCatchProbEngine,
    OutfieldPlayOpportunity,
    health_check,
)


def test_five_star_catch_opportunity_evaluates_properly():
    """Verify deep retreating catch with high speed req yields 5_STAR and high OAA."""
    engine = OutfieldCatchProbEngine()

    five_star = OutfieldPlayOpportunity(
        fielder_id="f1",
        fielder_name="Kevin Kiermaier Archetype",
        position="CF",
        distance_needed_ft=84.0,
        hang_time_s=3.9,
        direction_angle_deg=165.0,
        sprint_speed_fps=29.8,
        was_caught=True,
    )

    res = engine.evaluate_opportunity(five_star)

    assert res.catch_probability_pct < 20.0
    assert res.star_rating == "5_STAR"
    assert res.oaa_added > 0.80
    assert res.is_highlight_catch is True


def test_routine_catch_opportunity_evaluates_as_routine():
    """Verify short distance with high hang time yields ROUTINE tier."""
    engine = OutfieldCatchProbEngine()

    routine = OutfieldPlayOpportunity(
        fielder_id="f2",
        fielder_name="Routine Fielder",
        position="LF",
        distance_needed_ft=28.0,
        hang_time_s=5.0,
        direction_angle_deg=15.0,
        sprint_speed_fps=27.0,
        was_caught=True,
    )

    res = engine.evaluate_opportunity(routine)

    assert res.catch_probability_pct > 95.0
    assert res.star_rating == "ROUTINE"
    assert res.oaa_added < 0.05
    assert res.is_highlight_catch is False


def test_catch_prob_health_check():
    """Verify catch probability health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Catch prob verified" in checks[0].detail
