"""Unit tests for the real Chamberlain/Pavlidis VAA formula (VAA-01, ADR-180)."""

from mlb_baseball.model.vaa import health_check, pitch_vaa_degrees


def test_typical_four_seam_fastball_vaa_in_expected_range():
    """A typical modern four-seam's VAA should fall in the docstring's -4.5 to -6 deg range."""
    vaa = pitch_vaa_degrees(vy0=-130.0, ay=25.5, vz0=-5.8, az=-17.5)

    assert vaa is not None
    assert -6.5 <= vaa <= -4.0


def test_zero_ay_returns_none():
    """Degenerate kinematics (zero vertical acceleration) must return None, not crash."""
    assert pitch_vaa_degrees(vy0=-130.0, ay=0.0, vz0=-5.8, az=-17.5) is None


def test_negative_discriminant_returns_none():
    """An unphysical vy0 too small for the plate distance must return None, not raise."""
    assert pitch_vaa_degrees(vy0=-1.0, ay=25.5, vz0=-5.8, az=-17.5) is None


def test_vaa_health_check():
    """Verify VAA health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "VAA verified" in checks[0].detail
