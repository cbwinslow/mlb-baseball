"""Unit tests for Batter Contact Depth Kinematics Engine (CONTACT-DEPTH-01, ADR-191)."""

from mlb_baseball.model.contact_depth import (
    ContactDepthEngine,
    ContactKinematicsInput,
    health_check,
)


def test_pull_crusher_contact_depth_evaluates_properly():
    """Verify forward contact with high EV yields OUT_FRONT_PULL_CRUSHER."""
    engine = ContactDepthEngine()

    crusher = ContactKinematicsInput(
        batter_id="b1",
        batter_name="Jose Ramirez Archetype",
        contact_y_inches=7.5,
        pitch_velo_mph=95.0,
        pitch_location_x_inches=-4.0,
        spray_angle_deg=-28.0,
        exit_velo_mph=104.5,
        batter_side="R",
    )

    res = engine.evaluate_contact(crusher)

    assert res.contact_depth_in > 6.0
    assert res.timing_efficiency_pct > 80.0
    assert res.depth_tier == "OUT_FRONT_PULL_CRUSHER"
    assert res.is_out_front_slugger is True


def test_late_contact_triggers_timing_vulnerability():
    """Verify deep contact on fast inside pitch triggers LATE_TIMING_VULNERABILITY."""
    engine = ContactDepthEngine()

    late_hitter = ContactKinematicsInput(
        batter_id="b2",
        batter_name="Late Hitter",
        contact_y_inches=0.0,
        pitch_velo_mph=98.0,
        pitch_location_x_inches=-3.0,
        spray_angle_deg=18.0,
        exit_velo_mph=83.0,
        batter_side="R",
    )

    res = engine.evaluate_contact(late_hitter)

    assert res.depth_margin_in < -4.0
    assert res.depth_tier == "LATE_TIMING_VULNERABILITY"
    assert res.is_out_front_slugger is False


def test_contact_depth_health_check():
    """Verify contact depth health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Contact depth verified" in checks[0].detail
