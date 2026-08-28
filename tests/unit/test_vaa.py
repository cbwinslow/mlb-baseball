"""Unit tests for Pitcher Vertical Approach Angle Engine (VAA-01, ADR-180)."""

from mlb_baseball.model.vaa import (
    PitchApproachKinematics,
    VerticalApproachAngleEngine,
    health_check,
)


def test_high_rising_fastball_has_flat_vaa_and_whiff_boost():
    """Verify low release height with high IVB at top of zone yields flat VAA."""
    engine = VerticalApproachAngleEngine()

    rising_fb = PitchApproachKinematics(
        pitcher_id="p1",
        pitcher_name="Joe Ryan Archetype",
        pitch_type="FF",
        release_height_ft=5.4,
        plate_z_ft=3.4,
        pfx_z_in=20.0,
        release_velo_mph=95.0,
    )

    res = engine.evaluate_vaa(rising_fb)

    assert res.calculated_vaa_deg > -4.50
    assert res.whiff_boost_pct > 1.5
    assert res.approach_tier == "ELITE_FLAT_RISING_VAA"


def test_steep_downhill_pitch_classified_as_steep():
    """Verify tall release height with negative IVB yields steep downhill VAA."""
    engine = VerticalApproachAngleEngine()

    steep = PitchApproachKinematics(
        pitcher_id="p2",
        pitcher_name="Tall Curveballer",
        pitch_type="CU",
        release_height_ft=6.5,
        plate_z_ft=1.4,
        pfx_z_in=-12.0,
        release_velo_mph=79.0,
    )

    res = engine.evaluate_vaa(steep)

    assert res.calculated_vaa_deg < -7.00
    assert res.approach_tier == "STEEP_DOWNHILL"


def test_vaa_health_check():
    """Verify VAA health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "VAA verified" in checks[0].detail
