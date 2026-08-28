"""Unit tests for Outfielder Wall Crash Hazard Engine (WALL-CRASH-01, ADR-221)."""

from mlb_baseball.model.wall_crash import (
    OutfielderWallCrashEngine,
    OutfielderWallCrashMetrics,
    health_check,
)


def test_fearless_crasher_classified_properly():
    """Verify 80%+ wall catch rate yields FEARLESS_WALL_CRASH_DEFENDER."""
    engine = OutfielderWallCrashEngine()

    pca = OutfielderWallCrashMetrics(
        fielder_id="f1",
        fielder_name="Pete Crow-Armstrong Archetype",
        position="CF",
        wall_hazard_catch_pct=84.0,
        wall_collision_rate_pct=50.0,
        deceleration_cushion_ft=2.8,
        wall_opportunities=50,
    )

    res = engine.evaluate_wall_crash(pca)

    assert res.wcfi_score > 125.0
    assert res.surplus_catches > 8.0
    assert res.webpr_runs_saved > 7.0
    assert res.hazard_tier == "FEARLESS_WALL_CRASH_DEFENDER"
    assert res.is_fearless_crasher is True


def test_timid_pull_up_triggers_timid_tier():
    """Verify sub-52% wall catch rate triggers TIMID_WARNING_TRACK_PULL_UP."""
    engine = OutfielderWallCrashEngine()

    timid = OutfielderWallCrashMetrics(
        fielder_id="f2",
        fielder_name="Timid Warning Track Fielder",
        position="RF",
        wall_hazard_catch_pct=46.0,
        wall_collision_rate_pct=12.0,
        deceleration_cushion_ft=6.5,
        wall_opportunities=35,
    )

    res = engine.evaluate_wall_crash(timid)

    assert res.hazard_tier == "TIMID_WARNING_TRACK_PULL_UP"
    assert res.is_fearless_crasher is False


def test_default_metrics_produce_neutral_wcfi_score():
    """WALL-CRASH-01 regression: the class's own defaults (wall_hazard_catch_pct=65.0,
    wall_collision_rate_pct=30.0, deceleration_cushion_ft=4.6) are each documented as
    the benchmark in their own inline comments, but the WCFI formula was anchored at
    64.0/30.0/4.8 instead. Feeding the engine its own defaults should now produce an
    exactly neutral WCFI score of 100.0 and zero surplus catches.
    """
    engine = OutfielderWallCrashEngine()
    default_fielder = OutfielderWallCrashMetrics(fielder_id="f3", fielder_name="League Average")

    res = engine.evaluate_wall_crash(default_fielder)

    assert res.wcfi_score == 100.0
    assert res.surplus_catches == 0.0
    assert res.webpr_runs_saved == 0.0


def test_wall_crash_health_check():
    """Verify wall crash health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Wall Crash verified" in checks[0].detail
