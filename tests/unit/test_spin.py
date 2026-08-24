"""Unit tests for Pitched Ball Gyro Spin & Efficiency Decomposer (SPIN-01, ADR-157)."""

from mlb_baseball.model.spin import (
    PitchSpinObservation,
    SpinDecompositionEngine,
    health_check,
)


def test_four_seam_fastball_high_spin_efficiency():
    """Verify four-seam fastball with 95% efficiency isolates high transverse active spin."""
    engine = SpinDecompositionEngine()

    ff = PitchSpinObservation(
        pitch_id="p1",
        pitch_type="FF",
        total_spin_rpm=2450.0,
        spin_efficiency_pct=95.0,
    )

    res = engine.decompose_spin(ff)

    assert res.spin_archetype == "PURE_MAGNUS"
    assert res.active_spin_rpm > 2300.0
    assert res.gyro_spin_rpm < 800.0


def test_bullet_gyro_slider_low_spin_efficiency():
    """Verify bullet gyro-slider converts majority of spin into non-magnus bullet rotation."""
    engine = SpinDecompositionEngine()

    gyro_slider = PitchSpinObservation(
        pitch_id="p2",
        pitch_type="SL",
        total_spin_rpm=2700.0,
        spin_efficiency_pct=25.0,
    )

    res = engine.decompose_spin(gyro_slider)

    assert res.spin_archetype == "GYRO_BULLET"
    assert res.active_spin_rpm < 700.0
    assert res.gyro_spin_rpm > 2500.0


def test_spin_health_check():
    """Verify spin decomposition health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Spin verified" in checks[0].detail
