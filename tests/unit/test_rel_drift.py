"""Unit tests for Pitcher Release Point Variance Engine (REL-DRIFT-01, ADR-207)."""

from mlb_baseball.model.rel_drift import (
    PitcherReleaseDispersionMetrics,
    PitcherReleaseDriftEngine,
    health_check,
)


def test_metronomic_repeater_classified_properly():
    """Verify tight release standard deviation yields METRONOMIC_MECHANICAL_REPEATER."""
    engine = PitcherReleaseDriftEngine()

    greinke = PitcherReleaseDispersionMetrics(
        pitcher_id="p1",
        pitcher_name="Zack Greinke Archetype",
        mean_rel_x_ft=-2.10,
        mean_rel_z_ft=5.85,
        std_rel_x_in=1.1,
        std_rel_z_in=1.0,
        late_game_rel_drop_in=0.4,
        pitch_count_evaluated=100,
    )

    res = engine.evaluate_release_drift(greinke)

    assert res.spatial_dispersion_in <= 1.60
    assert res.mcs_score > 115.0
    assert res.release_tier == "METRONOMIC_MECHANICAL_REPEATER"
    assert res.is_metronomic_repeater is True
    assert res.fatigue_collapse_warning is False


def test_fatigued_arm_slot_drop_triggers_collapse_alert():
    """Verify large late game arm slot drop triggers FATIGUE_ARM_SLOT_COLLAPSE_ALERT."""
    engine = PitcherReleaseDriftEngine()

    fatigued = PitcherReleaseDispersionMetrics(
        pitcher_id="p2",
        pitcher_name="Tired Starter",
        mean_rel_x_ft=-2.10,
        mean_rel_z_ft=5.85,
        std_rel_x_in=1.9,
        std_rel_z_in=2.0,
        late_game_rel_drop_in=2.9,
        pitch_count_evaluated=85,
    )

    res = engine.evaluate_release_drift(fatigued)

    assert res.release_tier == "FATIGUE_ARM_SLOT_COLLAPSE_ALERT"
    assert res.fatigue_collapse_warning is True
    assert res.is_metronomic_repeater is False


def test_rel_drift_health_check():
    """Verify release drift health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Release Drift verified" in checks[0].detail
