"""Unit tests for Seam-Shifted Wake Aerodynamics Engine (SSW-01, ADR-147)."""

from mlb_baseball.model.ssw import (
    PitchSpinKinematics,
    SeamShiftedWakeEngine,
    health_check,
)


def test_sinker_with_strong_seam_shifted_wake():
    """Verify sinker generates significant non-Magnus deviation and whiff boost."""
    engine = SeamShiftedWakeEngine()

    sinker = PitchSpinKinematics(
        pitch_id="p1",
        pitch_type="SI",
        velocity_mph=95.0,
        spin_rate_rpm=2200,
        observed_ivb_in=5.0,
        observed_hb_in=18.0,
        spin_axis_deg=45.0,
    )

    res = engine.evaluate_pitch_ssw(sinker)

    assert res.ssw_total_magnitude_in > 2.5
    assert res.has_pronounced_ssw is True
    assert res.whiff_boost_pct > 3.0
    assert res.hard_hit_suppression_pct > 4.0


def test_four_seam_fastball_has_minimal_ssw():
    """Verify true four-seam fastball closely matches Magnus prediction."""
    engine = SeamShiftedWakeEngine()

    four_seam = PitchSpinKinematics(
        pitch_id="p2",
        pitch_type="FF",
        velocity_mph=96.0,
        spin_rate_rpm=2400,
        observed_ivb_in=18.0,
        observed_hb_in=3.0,
        spin_axis_deg=10.0,
    )

    res = engine.evaluate_pitch_ssw(four_seam)

    # 4-seam observed should be close to Magnus
    assert res.ssw_total_magnitude_in < 3.5


def test_ssw_health_check():
    """Verify SSW health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "SSW verified" in checks[0].detail
