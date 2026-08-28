"""Unit tests for Ballpark Environmental Carry & HR Scanner (CARRY-01, ADR-165)."""

from mlb_baseball.model.carry import (
    BallparkCarryScannerEngine,
    BattedBallTrajectory,
    health_check,
)


def test_short_porch_fly_ball_is_yankee_stadium_hr_only():
    """Verify 330 ft fly ball down right field line is a HR in Yankee Stadium but out in Wrigley."""
    engine = BallparkCarryScannerEngine()

    right_field_fly = BattedBallTrajectory(
        hit_id="h1",
        exit_velocity_mph=95.0,
        launch_angle_deg=34.0,
        spray_angle_deg=42.0,  # Right field corner
        nominal_distance_ft=330.0,
    )

    res = engine.scan_ballparks(right_field_fly)

    assert "Yankee Stadium" in res.home_run_venues
    assert "Wrigley Field" in res.out_venues
    assert res.parks_hr_count < res.total_parks_evaluated


def test_440_ft_crushed_blast_is_a_home_run_in_all_parks():
    """Verify deep blast clears fences in 100% of tested stadiums."""
    engine = BallparkCarryScannerEngine()

    crushed = BattedBallTrajectory(
        hit_id="h2",
        exit_velocity_mph=112.0,
        launch_angle_deg=28.0,
        spray_angle_deg=0.0,  # Straightaway center
        nominal_distance_ft=445.0,
    )

    res = engine.scan_ballparks(crushed)

    assert res.parks_hr_count == res.total_parks_evaluated
    assert res.hr_percentage == 100.0


def test_carry_health_check():
    """Verify carry health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Carry verified" in checks[0].detail
