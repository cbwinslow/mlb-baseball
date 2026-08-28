"""Unit tests for Catcher Wild Pitch & Passed Ball Wall Blocking Engine (WALL-BLOCK-01, ADR-249)."""

from mlb_baseball.model.wall_block import (
    CatcherWallBlockEngine,
    CatcherWallBlockMetrics,
    WallBlockEvaluationResult,
    health_check,
)


def test_brick_wall_classified_properly():
    """Verify 92%+ block and 95%+ suppress yields BRICK_WALL_DIRT_BALL_BLOCKER."""
    engine = CatcherWallBlockEngine()

    bailey = CatcherWallBlockMetrics(
        catcher_id="c1",
        catcher_name="Patrick Bailey Archetype",
        dirt_pitch_block_pct=95.0,
        runner_advance_suppress_pct=97.0,
        passed_ball_rate_per_1000=0.8,
        dirt_pitches_with_runners=160,
    )

    res: WallBlockEvaluationResult = engine.evaluate_wall_block(bailey)

    assert res.cwbei_score > 125.0
    assert res.brsaa_runs_saved > 14.0
    assert res.blocking_tier == "BRICK_WALL_DIRT_BALL_BLOCKER"
    assert res.is_brick_wall is True


def test_leaky_catcher_triggers_liability_tier():
    """Verify low block rate and high passed balls triggers OLE_OLE_DIRT_BALL_LEAK_LIABILITY."""
    engine = CatcherWallBlockEngine()

    leak = CatcherWallBlockMetrics(
        catcher_id="c2",
        catcher_name="Ole Catcher",
        dirt_pitch_block_pct=65.0,
        runner_advance_suppress_pct=70.0,
        passed_ball_rate_per_1000=6.5,
        dirt_pitches_with_runners=100,
    )

    res = engine.evaluate_wall_block(leak)

    assert res.blocking_tier == "OLE_OLE_DIRT_BALL_LEAK_LIABILITY"
    assert res.is_brick_wall is False


def test_wall_block_health_check():
    """Verify wall block health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Wall Block verified" in checks[0].detail
