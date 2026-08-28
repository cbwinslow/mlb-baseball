"""Unit tests for Catcher Block Suppress Engine (BLOCK-SUPPRESS-01, ADR-217)."""

from mlb_baseball.model.block_suppress import (
    CatcherBlockSuppressEngine,
    CatcherDirtBlockMetrics,
    health_check,
)


def test_brick_wall_catcher_classified_properly():
    """Verify 95%+ dirt block and sub-0.70s recovery yields BRICK_WALL_DIRT_SPECIALIST."""
    engine = CatcherBlockSuppressEngine()

    trevino = CatcherDirtBlockMetrics(
        catcher_id="c1",
        catcher_name="Jose Trevino Archetype",
        dirt_ball_block_pct=97.0,
        recovery_time_sec=0.62,
        runner_advance_prevention_pct=92.0,
        dirt_ball_opportunities=180,
    )

    res = engine.evaluate_blocking(trevino)

    assert res.dbwr_score > 125.0
    assert res.bapr_runs_saved > 8.0
    assert res.blocking_tier == "BRICK_WALL_DIRT_SPECIALIST"
    assert res.is_brick_wall is True


def test_leaky_blocker_triggers_liability_tier():
    """Verify sub-82% dirt block rate triggers LEAKY_DIRT_BALL_LIABILITY."""
    engine = CatcherBlockSuppressEngine()

    leaky = CatcherDirtBlockMetrics(
        catcher_id="c2",
        catcher_name="Leaky Blocker",
        dirt_ball_block_pct=78.0,
        recovery_time_sec=1.02,
        runner_advance_prevention_pct=62.0,
        dirt_ball_opportunities=120,
    )

    res = engine.evaluate_blocking(leaky)

    assert res.blocking_tier == "LEAKY_DIRT_BALL_LIABILITY"
    assert res.is_brick_wall is False


def test_block_suppress_health_check():
    """Verify block suppress health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Block Suppress verified" in checks[0].detail
