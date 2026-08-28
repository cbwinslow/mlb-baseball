"""Unit tests for Pitcher Acute-to-Chronic Workload Fatigue Engine (FATIGUE-01, ADR-161)."""

from mlb_baseball.model.fatigue import (
    PitcherFatigueEngine,
    PitcherWorkloadMetrics,
    health_check,
)


def test_overworked_starter_triggers_high_fatigue_overload():
    """Verify high acute workload spike and velocity decline trigger high fatigue risk."""
    engine = PitcherFatigueEngine()

    overused = PitcherWorkloadMetrics(
        pitcher_id="p1",
        pitcher_name="Overused Starter",
        pitches_7d=135,
        pitches_28d=300,
        velo_delta_mph=-1.5,
        release_drop_in=-1.7,
        high_stress_innings_count=3,
    )

    res = engine.evaluate_fatigue(overused)

    assert res.acwr_ratio > 1.20
    assert res.fatigue_risk_index > 60.0
    assert res.fatigue_tier == "HIGH_FATIGUE_OVERLOAD"
    assert res.is_velocity_flagged is True
    assert res.is_biomechanics_flagged is True


def test_well_conditioned_rested_pitcher_optimal_fitness():
    """Verify balanced workload and steady velocity evaluate to optimal fitness."""
    engine = PitcherFatigueEngine()

    rested = PitcherWorkloadMetrics(
        pitcher_id="p2",
        pitcher_name="Conditioned Ace",
        pitches_7d=90,
        pitches_28d=360,
        velo_delta_mph=0.3,
        release_drop_in=0.1,
        high_stress_innings_count=0,
    )

    res = engine.evaluate_fatigue(rested)

    assert res.acwr_ratio <= 1.05
    assert res.fatigue_risk_index < 30.0
    assert res.fatigue_tier == "OPTIMAL_FITNESS"
    assert res.is_velocity_flagged is False


def test_fatigue_health_check():
    """Verify fatigue health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Fatigue verified" in checks[0].detail
