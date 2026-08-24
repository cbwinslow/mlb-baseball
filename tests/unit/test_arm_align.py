"""Unit tests for Pitcher Arm Slot Stability Engine (ARM-ALIGN-01, ADR-220)."""

from mlb_baseball.model.arm_align import (
    ArmAlignEvaluationResult,
    PitcherArmAlignEngine,
    PitcherArsenalArmSlotMetrics,
    health_check,
)


def test_slot_clone_pitcher_classified_as_deceptive_clone():
    """Verify tightly aligned arm slots across arsenal yields DECEPTIVE_TUNNELED_ARM_SLOT_CLONE."""
    engine = PitcherArmAlignEngine()

    strider = PitcherArsenalArmSlotMetrics(
        pitcher_id="p1",
        pitcher_name="Spencer Strider Archetype",
        fastball_arm_angle_deg=42.0,
        breaking_arm_angle_deg=42.5,
        offspeed_arm_angle_deg=41.8,
        fastball_rel_z_in=68.0,
        breaking_rel_z_in=67.6,
        offspeed_rel_z_in=68.2,
        pitch_count_evaluated=300,
    )

    res: ArmAlignEvaluationResult = engine.evaluate_alignment(strider)

    assert res.max_arm_angle_gap_deg < 1.0
    assert res.max_rel_z_gap_in < 1.0
    assert res.aaar_score > 125.0
    assert res.tipping_risk_multiplier == 1.00
    assert res.alignment_tier == "DECEPTIVE_TUNNELED_ARM_SLOT_CLONE"
    assert res.is_slot_clone is True


def test_dropped_elbow_triggers_tipping_alert_tier():
    """Verify large arm angle gaps trigger TELL_PRONE_DROPPED_ELBOW_ALERT."""
    engine = PitcherArmAlignEngine()

    elbow_dropper = PitcherArsenalArmSlotMetrics(
        pitcher_id="p2",
        pitcher_name="Dropped Elbow Pitcher",
        fastball_arm_angle_deg=46.0,
        breaking_arm_angle_deg=36.0,
        offspeed_arm_angle_deg=45.0,
        fastball_rel_z_in=70.0,
        breaking_rel_z_in=63.5,
        offspeed_rel_z_in=69.5,
        pitch_count_evaluated=220,
    )

    res = engine.evaluate_alignment(elbow_dropper)

    assert res.max_arm_angle_gap_deg >= 10.0
    assert res.tipping_risk_multiplier > 1.30
    assert res.alignment_tier == "TELL_PRONE_DROPPED_ELBOW_ALERT"
    assert res.is_slot_clone is False


def test_arm_align_health_check():
    """Verify arm align health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Arm Align verified" in checks[0].detail
