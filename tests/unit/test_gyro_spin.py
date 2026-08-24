"""Unit tests for Pitcher Gyro Degree & True Spin Engine (GYRO-SPIN-01, ADR-195)."""

from mlb_baseball.model.gyro_spin import (
    PitchGyroSpinEngine,
    PitchGyroSpinMetrics,
    health_check,
)


def test_pure_bullet_gyro_slider_evaluates_properly():
    """Verify low spin efficiency yields high gyro angle and PURE_BULLET_GYRO tier."""
    engine = PitchGyroSpinEngine()

    bullet_sl = PitchGyroSpinMetrics(
        pitcher_id="p1",
        pitcher_name="Bullet Slider Pitcher",
        pitch_type="SL",
        total_spin_rpm=2750.0,
        spin_efficiency_pct=15.0,
        release_velo_mph=88.5,
        pfx_x_in=1.0,
        pfx_z_in=-1.5,
    )

    res = engine.evaluate_gyro_spin(bullet_sl)

    assert res.gyro_angle_deg > 80.0
    assert res.active_spin_rpm < 500.0
    assert res.gyro_spin_rpm > 2600.0
    assert res.aerodynamic_tier == "PURE_BULLET_GYRO"
    assert res.is_pure_bullet_gyro is True


def test_high_efficiency_fastball_evaluates_as_magnus():
    """Verify high spin efficiency yields low gyro angle and HIGH_EFFICIENCY_MAGNUS."""
    engine = PitchGyroSpinEngine()

    fastball = PitchGyroSpinMetrics(
        pitcher_id="p2",
        pitcher_name="High Spin Fastball Pitcher",
        pitch_type="FF",
        total_spin_rpm=2500.0,
        spin_efficiency_pct=98.0,
        release_velo_mph=97.5,
        pfx_x_in=-6.0,
        pfx_z_in=19.0,
    )

    res = engine.evaluate_gyro_spin(fastball)

    assert res.gyro_angle_deg < 15.0
    assert res.active_spin_rpm > 2400.0
    assert res.aerodynamic_tier == "HIGH_EFFICIENCY_MAGNUS"
    assert res.is_pure_bullet_gyro is False


def test_gyro_spin_health_check():
    """Verify gyro spin health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Gyro spin verified" in checks[0].detail
