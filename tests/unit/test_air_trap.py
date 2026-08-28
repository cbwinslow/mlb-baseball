"""Unit tests for Batter Pull-Side Air Warning Track Trap Engine (AIR-TRAP-01, ADR-227)."""

from mlb_baseball.model.air_trap import (
    AirTrapEvaluationResult,
    BatterAirTrapEngine,
    BatterAirTrapMetrics,
    health_check,
)


def test_pull_crusher_classified_properly():
    """Verify 30%+ clearance HR rate yields ELITE_WALL_CLEARING_PULL_CRUSHER."""
    engine = BatterAirTrapEngine()

    schwarber = BatterAirTrapMetrics(
        batter_id="b1",
        batter_name="Kyle Schwarber Archetype",
        pull_flyball_rate_pct=46.0,
        warning_track_trap_pct=12.0,
        wall_clearance_hr_pct=32.0,
        flyball_count=180,
    )

    res: AirTrapEvaluationResult = engine.evaluate_air_trap(schwarber)

    assert res.pacdtr_score > 125.0
    assert res.tthrd_runs_lost > 0.0  # Actually positive surplus runs
    assert res.trap_tier == "ELITE_WALL_CLEARING_PULL_CRUSHER"
    assert res.is_elite_clearer is True


def test_trapped_power_triggers_victim_tier():
    """Verify 30%+ warning track trap triggers WARNING_TRACK_POWER_TRAPPED_VICTIM."""
    engine = BatterAirTrapEngine()

    trapped = BatterAirTrapMetrics(
        batter_id="b2",
        batter_name="Warning Track Flyball Hitter",
        pull_flyball_rate_pct=34.0,
        warning_track_trap_pct=34.0,
        wall_clearance_hr_pct=8.0,
        flyball_count=130,
    )

    res = engine.evaluate_air_trap(trapped)

    assert res.tthrd_runs_lost < -10.0
    assert res.trap_tier == "WARNING_TRACK_POWER_TRAPPED_VICTIM"
    assert res.is_elite_clearer is False


def test_air_trap_health_check():
    """Verify air trap health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Air Trap verified" in checks[0].detail
