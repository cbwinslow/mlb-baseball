"""Unit tests for Pitcher Active Spin Efficiency Engine (ACTIVE-SPIN-01, ADR-224)."""

from mlb_baseball.model.active_spin import (
    ActiveSpinEvaluationResult,
    PitcherActiveSpinEngine,
    PitcherActiveSpinMetrics,
    health_check,
)


def test_pure_magnus_four_seamer_classified_properly():
    """Verify 98%+ active spin four-seamer yields PURE_TRANSVERSE_MAGNUS_RIDER."""
    engine = PitcherActiveSpinEngine()

    skenes = PitcherActiveSpinMetrics(
        pitcher_id="p1",
        pitcher_name="Paul Skenes Archetype",
        pitch_type="4-Seam",
        total_spin_rpm=2500.0,
        inferred_active_spin_rpm=2460.0,
        observed_ivb_in=19.8,
        observed_hb_in=9.5,
        pitch_count_evaluated=300,
    )

    res: ActiveSpinEvaluationResult = engine.evaluate_active_spin(skenes)

    assert res.active_spin_pct > 95.0
    assert res.gyro_angle_deg < 15.0
    assert res.asmi_score > 125.0
    assert res.spin_tier == "PURE_TRANSVERSE_MAGNUS_RIDER"
    assert res.is_pure_magnus is True


def test_bullet_slider_triggers_gyro_spinner_tier():
    """Verify sub-30% active spin slider triggers PURE_BULLET_GYRO_SPINNER."""
    engine = PitcherActiveSpinEngine()

    gyro_slider = PitcherActiveSpinMetrics(
        pitcher_id="p2",
        pitcher_name="Gyro Slider Specialist",
        pitch_type="Slider",
        total_spin_rpm=2450.0,
        inferred_active_spin_rpm=550.0,
        observed_ivb_in=0.5,
        observed_hb_in=-1.5,
        pitch_count_evaluated=220,
    )

    res = engine.evaluate_active_spin(gyro_slider)

    assert res.active_spin_pct < 25.0
    assert res.gyro_angle_deg > 70.0
    assert res.spin_tier == "PURE_BULLET_GYRO_SPINNER"
    assert res.is_pure_magnus is False


def test_active_spin_health_check():
    """Verify active spin health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Active Spin verified" in checks[0].detail
