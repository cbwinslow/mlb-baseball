"""Unit tests for Pitcher Arm Slot Fatigue Sag Engine (SLOT-SAG-01, ADR-252)."""

from mlb_baseball.model.slot_sag import (
    PitcherSlotSagEngine,
    PitcherSlotSagMetrics,
    SlotSagEvaluationResult,
    health_check,
)


def test_slot_replicator_classified_properly():
    """Verify under 0.8 deg drop and 0.8 in drift yields IRON_SHOULDER_SLOT_REPLICATOR."""
    engine = PitcherSlotSagEngine()

    wheeler = PitcherSlotSagMetrics(
        pitcher_id="p1",
        pitcher_name="Zack Wheeler Archetype",
        early_arm_slot_angle_deg=45.0,
        late_arm_slot_angle_deg=44.8,
        early_release_x_in=-23.0,
        late_release_x_in=-23.3,
        late_pitches_thrown=45,
    )

    res: SlotSagEvaluationResult = engine.evaluate_slot_sag(wheeler)

    assert res.asfsi_score > 105.0
    assert res.fsdrs_runs_saved > 0.5
    assert res.sag_tier == "IRON_SHOULDER_SLOT_REPLICATOR"
    assert res.is_slot_replicator is True


def test_collapsing_slot_triggers_liability_tier():
    """Verify large slot drop triggers COLLAPSING_SLOT_DROPPING_FATIGUE_LIABILITY."""
    engine = PitcherSlotSagEngine()

    fatigued = PitcherSlotSagMetrics(
        pitcher_id="p2",
        pitcher_name="Slot Collapser",
        early_arm_slot_angle_deg=50.0,
        late_arm_slot_angle_deg=43.0,
        early_release_x_in=-22.0,
        late_release_x_in=-28.0,
        late_pitches_thrown=30,
    )

    res = engine.evaluate_slot_sag(fatigued)

    assert res.sag_tier == "COLLAPSING_SLOT_DROPPING_FATIGUE_LIABILITY"
    assert res.is_slot_replicator is False


def test_slot_sag_health_check():
    """Verify slot sag health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Slot Sag verified" in checks[0].detail
