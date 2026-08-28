"""Unit tests for Catcher Blocking Run Value Modeler (BLOCK-01, ADR-148)."""

from mlb_baseball.model.blocking import (
    CatcherBlockingEngine,
    CatcherBlockProfile,
    PitcherSpikeProfile,
    health_check,
)


def test_elite_blocking_catcher_suppresses_passed_balls_and_runs():
    """Verify elite blocking catcher prevents run advancement on spike pitchers."""
    engine = CatcherBlockingEngine()

    elite_catcher = CatcherBlockProfile("c1", "Elite Wall", blocking_runs_above_avg=5.0)
    spike_pitcher = PitcherSpikeProfile("p1", "Sweeper Specialist", dirt_pitches_per_game=14.0)

    res = engine.evaluate_blocking_matchup(elite_catcher, spike_pitcher)

    assert res.blocking_tier == "ELITE_WALL"
    assert res.expected_blocks_per_game > 13.0
    assert res.expected_passed_balls_per_game < 0.10
    assert res.run_cost_delta_per_game < 0.0  # Run prevention


def test_vulnerable_catcher_concedes_excess_misses():
    """Verify negative blocking catcher allows higher missed balls and run cost."""
    engine = CatcherBlockingEngine()

    poor_catcher = CatcherBlockProfile("c2", "Poor Blocker", blocking_runs_above_avg=-5.0)
    spike_pitcher = PitcherSpikeProfile("p1", "Sweeper Specialist", dirt_pitches_per_game=14.0)

    res = engine.evaluate_blocking_matchup(poor_catcher, spike_pitcher)

    assert res.blocking_tier == "VULNERABLE"
    assert res.expected_passed_balls_per_game > 0.20
    assert res.run_cost_delta_per_game > 0.05  # Concedes runs


def test_negative_five_runs_matches_documented_block_rate():
    """BLOCK-01 regression (cosmetic): the module's comment used to claim -5.0 runs
    produces an 89.0% block rate, but the real symmetric formula
    (0.940 + (runs/10.0)*0.070) produces 90.5%, matching the now-corrected comment.
    Verify the real number directly via a clean 10-dirt-pitch sample
    (10 * 0.905 block rate = 9.05 expected blocks).
    """
    engine = CatcherBlockingEngine()
    catcher = CatcherBlockProfile("c3", "Porous Blocker", blocking_runs_above_avg=-5.0)
    pitcher = PitcherSpikeProfile("p3", "Clean Ten", dirt_pitches_per_game=10.0)

    res = engine.evaluate_blocking_matchup(catcher, pitcher)

    assert res.expected_blocks_per_game == 9.05


def test_blocking_health_check():
    """Verify blocking health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Blocking verified" in checks[0].detail
