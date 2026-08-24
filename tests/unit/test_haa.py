"""Unit tests for Pitcher Horizontal Approach Angle Engine (HAA-01, ADR-184)."""

from mlb_baseball.model.haa import (
    HorizontalApproachAngleEngine,
    PitchHorizontalKinematics,
    health_check,
)


def test_cross_fire_sweeper_triggers_extreme_cross_fire_sweep():
    """Verify wide release point with heavy sweep yields extreme HAA and deception score."""
    engine = HorizontalApproachAngleEngine()

    sweeper = PitchHorizontalKinematics(
        pitcher_id="p1",
        pitcher_name="Sweeper Specialist",
        pitch_type="ST",
        release_x_ft=-2.7,
        plate_x_ft=0.9,
        pfx_x_in=18.5,
        release_velo_mph=83.5,
    )

    res = engine.evaluate_haa(sweeper)

    assert abs(res.calculated_haa_deg) > 3.0
    assert res.cross_body_deception_score > 60.0
    assert res.haa_tier == "EXTREME_CROSS_FIRE_SWEEP"


def test_standard_overhand_pitcher_classified_as_standard():
    """Verify narrow release with minimal horizontal movement yields STANDARD tier."""
    engine = HorizontalApproachAngleEngine()

    overhand = PitchHorizontalKinematics(
        pitcher_id="p2",
        pitcher_name="Overhand Pitcher",
        pitch_type="FF",
        release_x_ft=-0.7,
        plate_x_ft=0.0,
        pfx_x_in=2.0,
        release_velo_mph=95.0,
    )

    res = engine.evaluate_haa(overhand)

    assert abs(res.calculated_haa_deg) < 1.5
    assert res.haa_tier == "STANDARD"


def test_haa_health_check():
    """Verify HAA health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "HAA verified" in checks[0].detail
