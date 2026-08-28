"""Unit tests for Batter Oppo-Field Power & Alley Extra-Base Gap (OPPO-GAP-01, ADR-239)."""

from mlb_baseball.model.oppo_gap import (
    BatterOppoGapEngine,
    BatterOppoGapMetrics,
    OppoGapEvaluationResult,
    health_check,
)


def test_oppo_monster_classified_properly():
    """Verify 15%+ oppo XBH and 50%+ hard-hit yields ELITE_ALL_FIELDS_POWER_MONSTER."""
    engine = BatterOppoGapEngine()

    judge = BatterOppoGapMetrics(
        batter_id="b1",
        batter_name="Aaron Judge Archetype",
        oppo_contact_pct=34.0,
        oppo_hard_hit_pct=54.0,
        oppo_extra_base_hit_pct=17.0,
        oppo_batted_balls_count=140,
    )

    res: OppoGapEvaluationResult = engine.evaluate_oppo_gap(judge)

    assert res.ofgpi_score > 125.0
    assert res.aebr_runs_produced > 12.0
    assert res.oppo_tier == "ELITE_ALL_FIELDS_POWER_MONSTER"
    assert res.is_elite_monster is True


def test_pull_dependent_slapper_triggers_slapper_tier():
    """Verify sub-5% oppo XBH and low hard hit triggers PULL_DEPENDENT_OPPO_SLAPPER."""
    engine = BatterOppoGapEngine()

    slapper = BatterOppoGapMetrics(
        batter_id="b2",
        batter_name="Pull Heavy Slapper",
        oppo_contact_pct=18.0,
        oppo_hard_hit_pct=19.0,
        oppo_extra_base_hit_pct=3.5,
        oppo_batted_balls_count=80,
    )

    res = engine.evaluate_oppo_gap(slapper)

    assert res.oppo_tier == "PULL_DEPENDENT_OPPO_SLAPPER"
    assert res.is_elite_monster is False


def test_oppo_gap_health_check():
    """Verify oppo gap health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Oppo Gap verified" in checks[0].detail
