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


def test_green_monster_turns_a_short_porch_fly_ball_into_an_out():
    """A fly ball that would clear a standard 8ft fence at Fenway's 310ft LF
    line is caught up short by the real 37ft Green Monster (bug fix,
    2026-09-19, issue #220: lf_wall_h/rf_wall_h previously had zero effect)."""
    engine = BallparkCarryScannerEngine()

    marginal_fly = BattedBallTrajectory(
        hit_id="h3",
        exit_velocity_mph=93.0,
        launch_angle_deg=30.0,
        spray_angle_deg=-45.0,  # Straight down the left field line
        nominal_distance_ft=320.0,  # Clears 310ft + the old flat 4ft margin
    )

    res = engine.scan_ballparks(marginal_fly)

    assert "Fenway Park" in res.out_venues
    assert "Fenway Park" not in res.home_run_venues


def test_deep_enough_fly_ball_still_clears_the_green_monster():
    """A genuinely deep shot down the line still clears even a 37ft wall."""
    engine = BallparkCarryScannerEngine()

    deep_fly = BattedBallTrajectory(
        hit_id="h4",
        exit_velocity_mph=105.0,
        launch_angle_deg=30.0,
        spray_angle_deg=-45.0,
        nominal_distance_ft=350.0,
    )

    res = engine.scan_ballparks(deep_fly)

    assert "Fenway Park" in res.home_run_venues


def test_carry_health_check():
    """Verify carry health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Carry verified" in checks[0].detail
