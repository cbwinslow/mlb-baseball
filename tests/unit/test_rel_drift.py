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
    # REL-DRIFT-01 fix: the MCS formula's dispersion anchor now matches the class's own
    # defaults (2.41 in, not the old unreconciled 2.6 in), which shifts every mcs_score
    # down by ~3 points at a given dispersion level. 110.0 keeps a solid margin above
    # the class's own is_metronomic_repeater gate (>=112.0).
    assert res.mcs_score > 110.0
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


def test_default_metrics_produce_neutral_mcs_score():
    """REL-DRIFT-01 regression: the class's own defaults (std_rel_x_in=1.8,
    std_rel_z_in=1.6) compute spatial_dispersion_in = sqrt(1.8^2+1.6^2) = 2.41 in, and
    late_game_rel_drop_in defaults to the no-penalty 0.8 in. Feeding the engine its own
    defaults should now produce an exactly neutral MCS score of 100.0, not the ~103 the
    old, unreconciled 2.6 in anchor produced.
    """
    engine = PitcherReleaseDriftEngine()
    default_pitcher = PitcherReleaseDispersionMetrics(pitcher_id="p3", pitcher_name="Average")

    res = engine.evaluate_release_drift(default_pitcher)

    assert res.spatial_dispersion_in == 2.41
    assert res.mcs_score == 100.0


def test_rel_drift_health_check():
    """Verify release drift health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Release Drift verified" in checks[0].detail
