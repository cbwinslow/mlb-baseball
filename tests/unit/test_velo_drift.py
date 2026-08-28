"""Unit tests for Starting Pitcher Fastball Velocity Drift Engine (VELO-DRIFT-01, ADR-188)."""

from mlb_baseball.model.velo_drift import (
    FastballVeloDriftEngine,
    PitcherVeloProfile,
    health_check,
)


def test_workhorse_pitcher_maintains_velocity_and_high_fvri():
    """Verify minimal velo drop yields ELITE_VELO_PRESERVATION and low HR multiplier."""
    engine = FastballVeloDriftEngine()

    workhorse = PitcherVeloProfile(
        pitcher_id="p1",
        pitcher_name="Justin Verlander Archetype",
        early_game_velo_mph=96.8,
        late_game_velo_mph=96.4,
        pitch_count_total=105,
        early_spin_rpm=2480.0,
        late_spin_rpm=2460.0,
    )

    res = engine.evaluate_velo_drift(workhorse)

    assert res.velo_drift_mph > -0.50
    assert res.fvri_score >= 88.0
    assert res.hr_vulnerability_multiplier < 1.10
    assert res.fatigue_tier == "ELITE_VELO_PRESERVATION"
    assert res.is_severe_hook_candidate is False


def test_fatigued_arm_triggers_severe_velo_cliff_and_hook_alert():
    """Verify sharp velo degradation triggers SEVERE_VELO_CLIFF and hook flag."""
    engine = FastballVeloDriftEngine()

    fatigued = PitcherVeloProfile(
        pitcher_id="p2",
        pitcher_name="Gassed Starter",
        early_game_velo_mph=95.8,
        late_game_velo_mph=92.5,
        pitch_count_total=88,
        early_spin_rpm=2400.0,
        late_spin_rpm=2200.0,
    )

    res = engine.evaluate_velo_drift(fatigued)

    assert res.velo_drift_mph < -3.0
    assert res.fvri_score < 45.0
    assert res.hr_vulnerability_multiplier > 1.60
    assert res.fatigue_tier == "SEVERE_VELO_CLIFF"
    assert res.is_severe_hook_candidate is True


def test_velo_drift_health_check():
    """Verify velocity drift health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Velo drift verified" in checks[0].detail
