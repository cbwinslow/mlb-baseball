"""Unit tests for Outfielder First-Step Reaction Burst Engine (FIRST-STEP-01, ADR-237)."""

from mlb_baseball.model.first_step import (
    FirstStepEvaluationResult,
    OutfielderFirstStepEngine,
    OutfielderFirstStepMetrics,
    health_check,
)


def test_ballhawk_burster_classified_properly():
    """Verify sub-0.30s reaction and 36ft+ burst yields ELITE_INSTINCTIVE_BALLHAWK_BURSTER."""
    engine = OutfielderFirstStepEngine()

    kiermaier = OutfielderFirstStepMetrics(
        fielder_id="f1",
        fielder_name="Kevin Kiermaier Archetype",
        position="CF",
        reaction_time_sec=0.25,
        distance_first_1_5s_ft=37.5,
        route_jump_efficiency_pct=96.0,
        outfield_flyball_chances=160,
    )

    res: FirstStepEvaluationResult = engine.evaluate_first_step(kiermaier)

    assert res.fsrji_score > 125.0
    assert res.jrp_runs_prevented > 10.0
    assert res.jump_tier == "ELITE_INSTINCTIVE_BALLHAWK_BURSTER"
    assert res.is_elite_burster is True


def test_hesitant_fielder_triggers_liability_tier():
    """Verify 0.54s+ reaction and short burst triggers HESITANT_SLOW_FIRST_STEP_LIABILITY."""
    engine = OutfielderFirstStepEngine()

    hesitant = OutfielderFirstStepMetrics(
        fielder_id="f2",
        fielder_name="Hesitant Outfielder",
        position="LF",
        reaction_time_sec=0.56,
        distance_first_1_5s_ft=27.5,
        route_jump_efficiency_pct=78.0,
        outfield_flyball_chances=100,
    )

    res = engine.evaluate_first_step(hesitant)

    assert res.jump_tier == "HESITANT_SLOW_FIRST_STEP_LIABILITY"
    assert res.is_elite_burster is False


def test_first_step_health_check():
    """Verify first step health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "First Step verified" in checks[0].detail
