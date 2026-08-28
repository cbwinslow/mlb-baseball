"""Unit tests for Outfielder Wall Leap & Timing Elevation Engine (WALL-LEAP-01, ADR-253)."""

from mlb_baseball.model.wall_leap import (
    OutfielderWallLeapEngine,
    OutfielderWallLeapMetrics,
    WallLeapEvaluationResult,
    health_check,
)


def test_wall_thief_classified_properly():
    """Verify 26+ in apex and 60%+ catch yields GRAVITY_DEFYING_WALL_THIEF."""
    engine = OutfielderWallLeapEngine()

    pillar = OutfielderWallLeapMetrics(
        fielder_id="f1",
        fielder_name="Kevin Pillar Archetype",
        vertical_leap_apex_in=28.0,
        leap_timing_precision_ms=45.0,
        above_wall_catch_pct=65.0,
        wall_leap_opportunities=16,
    )

    res: WallLeapEvaluationResult = engine.evaluate_wall_leap(pillar)

    assert res.wltei_score > 125.0
    assert res.rrvaa_runs_saved > 3.0
    assert res.leap_tier == "GRAVITY_DEFYING_WALL_THIEF"
    assert res.is_wall_thief is True


def test_ground_bound_triggers_liability_tier():
    """Verify low apex and low catch rate triggers GROUND_BOUND_MISTIMED_LEAP_LIABILITY."""
    engine = OutfielderWallLeapEngine()

    ground = OutfielderWallLeapMetrics(
        fielder_id="f2",
        fielder_name="Ground Bound Fielder",
        vertical_leap_apex_in=10.0,
        leap_timing_precision_ms=130.0,
        above_wall_catch_pct=15.0,
        wall_leap_opportunities=10,
    )

    res = engine.evaluate_wall_leap(ground)

    assert res.leap_tier == "GROUND_BOUND_MISTIMED_LEAP_LIABILITY"
    assert res.is_wall_thief is False


def test_wall_leap_health_check():
    """Verify wall leap health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Wall Leap verified" in checks[0].detail
