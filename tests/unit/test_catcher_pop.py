"""Unit tests for Catcher Block-to-Throw & Pop Engine (CATCHER-POP-01, ADR-193)."""

from mlb_baseball.model.catcher_pop import (
    CatcherPopAndBlockEngine,
    CatcherPopAndBlockMetrics,
    health_check,
)


def test_elite_catcher_classified_as_wall_and_cannon():
    """Verify sub-1.90s pop time and high dirt CS yields WALL_AND_CANNON_BACKSTOP."""
    engine = CatcherPopAndBlockEngine()

    realmuto = CatcherPopAndBlockMetrics(
        catcher_id="c1",
        catcher_name="J.T. Realmuto Archetype",
        clean_pop_time_s=1.87,
        block_recovery_time_s=0.58,
        dirt_throw_velo_mph=87.0,
        blocked_pitches_count=80,
        wild_pitches_prevented=22,
        dirt_caught_stealing=5,
        passed_balls=0,
    )

    res = engine.evaluate_catcher(realmuto)

    assert res.total_block_throw_time_s < 2.50
    assert res.advancement_deterrence_pct > 80.0
    assert res.btsv_runs_saved > 5.0
    assert res.catcher_tier == "WALL_AND_CANNON_BACKSTOP"
    assert res.is_elite_backstop is True


def test_slow_catcher_triggers_liability_tier():
    """Verify high pop time and multiple passed balls triggers SLOW_RECOVERY_LIABILITY."""
    engine = CatcherPopAndBlockEngine()

    slow_c = CatcherPopAndBlockMetrics(
        catcher_id="c2",
        catcher_name="Defensive Liability",
        clean_pop_time_s=2.12,
        block_recovery_time_s=0.90,
        dirt_throw_velo_mph=77.0,
        blocked_pitches_count=35,
        wild_pitches_prevented=3,
        dirt_caught_stealing=0,
        passed_balls=5,
    )

    res = engine.evaluate_catcher(slow_c)

    assert res.btsv_runs_saved < 0.0
    assert res.catcher_tier == "SLOW_RECOVERY_LIABILITY"
    assert res.is_elite_backstop is False


def test_catcher_pop_health_check():
    """Verify catcher pop health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Catcher pop verified" in checks[0].detail
