"""Unit tests for Pitcher Arsenals Tunneling Engine (TUNNEL-01, ADR-152)."""

from mlb_baseball.model.tunnel import (
    PitchFlightVector,
    PitchTunnelingEngine,
    health_check,
)


def test_tight_tunneling_fastball_slider_pair_generates_whiff_boost():
    """Verify identical release point with late break separation produces elite tunneling score."""
    engine = PitchTunnelingEngine()

    ff = PitchFlightVector(
        "FF", velocity_mph=97.0, release_x_ft=-2.0, release_z_ft=6.0, ivb_in=18.0, hb_in=12.0
    )
    sl = PitchFlightVector(
        "SL", velocity_mph=87.0, release_x_ft=-2.0, release_z_ft=6.0, ivb_in=1.0, hb_in=-10.0
    )

    res = engine.evaluate_tunnel_pair(ff, sl)

    assert res.release_distance_in == 0.0
    assert res.plate_break_separation_in > 25.0
    assert res.tunnel_distance_at_poc_in < 10.0
    assert res.tunneling_quality_score > 50.0


def test_mismatched_release_point_penalizes_tunneling():
    """Verify different arm slots or release positions degrade tunneling score."""
    engine = PitchTunnelingEngine()

    ff = PitchFlightVector(
        "FF", velocity_mph=95.0, release_x_ft=-2.0, release_z_ft=6.2, ivb_in=16.0, hb_in=10.0
    )
    # Sidearm slider / dropped arm slot:
    sl = PitchFlightVector(
        "SL", velocity_mph=84.0, release_x_ft=-3.2, release_z_ft=4.8, ivb_in=-2.0, hb_in=-12.0
    )

    res = engine.evaluate_tunnel_pair(ff, sl)

    assert res.release_distance_in > 15.0  # > 15 inches release distance
    assert res.is_elite_tunnel is False


def test_tunnel_health_check():
    """Verify pitch tunneling health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Tunnel verified" in checks[0].detail
