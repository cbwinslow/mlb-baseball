"""Unit tests for Batter Pull Line-Drive Slice Power Engine (PULL-SLICE-01, ADR-235)."""

from mlb_baseball.model.pull_slice import (
    BatterPullSliceEngine,
    BatterPullSliceMetrics,
    PullSliceEvaluationResult,
    health_check,
)


def test_pull_surgeon_classified_properly():
    """Verify 84%+ fair conversion and high hard-hit yields ELITE_DOWN_THE_LINE_PULL_SURGEON."""
    engine = BatterPullSliceEngine()

    betts = BatterPullSliceMetrics(
        batter_id="b1",
        batter_name="Mookie Betts Archetype",
        pull_ld_rate_pct=28.0,
        fair_pole_conversion_pct=86.0,
        pull_ld_hard_hit_pct=70.0,
        pull_ld_opportunities=110,
    )

    res: PullSliceEvaluationResult = engine.evaluate_pull_slice(betts)

    assert res.pldsr_score > 125.0
    assert res.fpebr_runs_produced > 10.0
    assert res.slice_tier == "ELITE_DOWN_THE_LINE_PULL_SURGEON"
    assert res.is_elite_surgeon is True


def test_hooking_slicer_triggers_hook_tier():
    """Verify sub-58% fair conversion triggers HOOKING_FOUL_BALL_SLICER."""
    engine = BatterPullSliceEngine()

    hooker = BatterPullSliceMetrics(
        batter_id="b2",
        batter_name="Hooking Pull Slicer",
        pull_ld_rate_pct=18.0,
        fair_pole_conversion_pct=52.0,
        pull_ld_hard_hit_pct=44.0,
        pull_ld_opportunities=70,
    )

    res = engine.evaluate_pull_slice(hooker)

    assert res.slice_tier == "HOOKING_FOUL_BALL_SLICER"
    assert res.is_elite_surgeon is False


def test_pull_slice_health_check():
    """Verify pull slice health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Pull Slice verified" in checks[0].detail
