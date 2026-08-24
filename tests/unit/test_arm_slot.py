"""Unit tests for Pitcher Arm Slot Angle & Release Consistency Engine (ARM-SLOT-01, ADR-192)."""

from mlb_baseball.model.arm_slot import (
    PitcherArmSlotEngine,
    PitcherArmSlotMetrics,
    health_check,
)


def test_sidearm_pitcher_evaluates_as_sidearm():
    """Verify low vertical release relative to shoulder yields SIDEARM tier."""
    engine = PitcherArmSlotEngine()

    sidearmer = PitcherArmSlotMetrics(
        pitcher_id="p1",
        pitcher_name="Sidearm Specialist",
        release_x_ft=-2.5,
        release_z_ft=5.2,
        pitcher_height_in=73.0,
        release_dispersion_std_in=1.1,
    )

    res = engine.evaluate_arm_slot(sidearmer)

    assert 70.0 <= res.arm_slot_angle_deg <= 90.0
    assert res.arm_slot_tier == "SIDEARM"
    assert res.release_consistency_score > 70.0


def test_overhand_pitcher_evaluates_as_over_the_top():
    """Verify high vertical release with narrow horizontal spread yields OVER_THE_TOP."""
    engine = PitcherArmSlotEngine()

    overhand = PitcherArmSlotMetrics(
        pitcher_id="p2",
        pitcher_name="Tyler Glasnow Archetype",
        release_x_ft=-0.5,
        release_z_ft=6.6,
        pitcher_height_in=78.0,
        release_dispersion_std_in=0.8,
    )

    res = engine.evaluate_arm_slot(overhand)

    assert res.arm_slot_angle_deg < 30.0
    assert res.arm_slot_tier == "OVER_THE_TOP"
    assert res.is_elite_release_tunnel is True


def test_arm_slot_health_check():
    """Verify arm slot health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Arm slot verified" in checks[0].detail
