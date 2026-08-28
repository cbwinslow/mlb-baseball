"""Unit tests for 2D Strike Zone KDE & Batted Ball Ballistics Engine (HEATMAP-01, ADR-127)."""

from mlb_baseball.model.heatmap import (
    AttackZone,
    BattedBallBallisticsEngine,
    StrikeZoneKDEMonitor,
    health_check,
)


def test_strike_zone_attack_zone_classification():
    """Verify attack zone classifications for Heart, Shadow, Chase, and Waste."""
    kde = StrikeZoneKDEMonitor()

    # Heart (dead center)
    assert kde.classify_attack_zone(0.0, 2.5) == AttackZone.HEART
    # Shadow (edge of plate)
    assert kde.classify_attack_zone(0.75, 2.5) == AttackZone.SHADOW
    # Chase (just outside shadow)
    assert kde.classify_attack_zone(1.20, 2.5) == AttackZone.CHASE
    # Waste (wild pitch)
    assert kde.classify_attack_zone(2.50, 4.8) == AttackZone.WASTE


def test_strike_zone_kde_density_grid():
    """Verify bivariate Gaussian KDE generates proper normalized probability density grid."""
    kde = StrikeZoneKDEMonitor()

    # Cluster of 30 pitches in upper right shadow zone
    px = [0.6, 0.7, 0.65, 0.8] * 10
    pz = [3.2, 3.4, 3.3, 3.1] * 10

    grid = kde.compute_density_grid(px, pz, grid_size=(15, 15))

    assert grid.rows == 15
    assert grid.cols == 15
    assert 0.5 <= grid.peak_density_coordinate[0] <= 0.9
    assert 2.8 <= grid.peak_density_coordinate[1] <= 3.6
    # Probability density elements should sum to ~1.0
    total_mass = sum(sum(row) for row in grid.density_matrix)
    assert 0.95 <= total_mass <= 1.05


def test_batted_ball_ballistics_barrel_trajectory():
    """Verify 108 mph barrel at 28 degrees projects ~410+ ft home run landing coordinates."""
    ballistics = BattedBallBallisticsEngine()

    hit = ballistics.compute_field_coordinates(
        hit_id="h1",
        exit_velocity_mph=108.0,
        launch_angle_deg=28.0,
        spray_angle_deg=-15.0,  # Left-center field
        air_density_index=100.0,
    )

    assert hit.is_barrel is True
    assert hit.is_hard_hit is True
    assert hit.distance_feet > 400.0
    assert hit.field_x_ft < 0.0  # Left field is negative x
    assert hit.field_y_ft > 300.0


def test_heatmap_health_check():
    """Verify heatmap health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "KDE grid & ballistics verified" in checks[0].detail
