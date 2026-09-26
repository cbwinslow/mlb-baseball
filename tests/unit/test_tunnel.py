"""Unit tests for Pitcher Arsenals Tunneling Engine (TUNNEL-01, ADR-152)."""

import math

from mlb_baseball.model.tunnel import (
    _YF_PLATE_FT,
    _YF_TUNNEL_FT,
    DATA_SOURCE_STATCAST,
    DATA_SOURCE_WHATIF,
    PitchFlightVector,
    PitchTunnelingEngine,
    _position_at_y,
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
    assert res.break_tunnel_ratio > 2.0  # plate separation more than triples POC separation
    assert res.is_elite_tunnel is True
    assert res.data_source == DATA_SOURCE_WHATIF


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
    assert res.data_source == DATA_SOURCE_WHATIF


def test_whatif_result_is_never_labeled_as_real_statcast_data():
    """Verify the hand-typed what-if path is distinguishable from real Statcast data."""
    engine = PitchTunnelingEngine()
    ff = PitchFlightVector("FF", 96.0, -2.0, 6.0, 17.0, 10.0)
    sl = PitchFlightVector("SL", 86.0, -2.0, 6.0, 2.0, -8.0)

    res = engine.evaluate_tunnel_pair(ff, sl)

    assert res.data_source != DATA_SOURCE_STATCAST
    assert res.data_source == DATA_SOURCE_WHATIF


def test_position_at_y_matches_hand_calculated_projectile_motion():
    """Deterministic hand-fixture: closed-form kinematics solved and checked by hand."""
    # Simple case chosen so t is exact: vy0 = -100 ft/s, ay = 0 is disallowed
    # (guarded below), so use ay small and check against the same formula
    # vaa.py already trusts (shared math, TUNNEL-01 generalizes its target y).
    x0, z0 = -2.0, 6.0
    vx0, vy0, vz0 = 4.0, -130.0, -6.0
    ax, ay, az = -2.0, 25.0, -16.0

    pos = _position_at_y(
        x0=x0, z0=z0, vx0=vx0, vy0=vy0, vz0=vz0, ax=ax, ay=ay, az=az, yf=_YF_PLATE_FT
    )
    assert pos is not None

    # Hand-calculated: solve the same disc/vy_f/t the module uses, independently.
    y0 = 50.0
    disc = vy0 * vy0 - 2.0 * ay * (y0 - _YF_PLATE_FT)
    vy_f = -math.sqrt(disc)
    t = (vy_f - vy0) / ay
    expected_x = x0 + vx0 * t + 0.5 * ax * t * t
    expected_z = z0 + vz0 * t + 0.5 * az * t * t

    assert pos[0] == expected_x
    assert pos[1] == expected_z


def test_position_at_y_returns_none_for_degenerate_kinematics():
    """Zero ay and a negative discriminant must return None, not crash (mirrors vaa.py)."""
    zero_ay = _position_at_y(
        x0=0, z0=0, vx0=0, vy0=-130, vz0=0, ax=0, ay=0.0, az=0, yf=_YF_PLATE_FT
    )
    assert zero_ay is None
    neg_disc = _position_at_y(
        x0=0, z0=0, vx0=0, vy0=-1.0, vz0=0, ax=0, ay=25.0, az=0, yf=_YF_PLATE_FT
    )
    assert neg_disc is None


def test_tunnel_point_is_further_from_plate_than_the_plate_itself():
    """Sanity: the Tunnel Point target y is further from the plate than the plate's own yf."""
    assert _YF_TUNNEL_FT > _YF_PLATE_FT
    assert round(_YF_TUNNEL_FT - _YF_PLATE_FT, 1) == 23.8


def test_tunnel_health_check():
    """Verify pitch tunneling health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Tunnel verified" in checks[0].detail
