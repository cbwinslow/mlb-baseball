"""Unit tests for Pitcher Release Point Spin Angle Stability Engine (SPIN-ALIGN-01, ADR-240)."""

from mlb_baseball.model.spin_align import (
    PitcherSpinAlignEngine,
    PitcherSpinAlignMetrics,
    SpinAlignEvaluationResult,
    health_check,
)


def test_spin_illusionist_classified_properly():
    """Verify tightly clustered release and spin axis yields MIRRORED_SPIN_TUNNEL_ILLUSIONIST."""
    engine = PitcherSpinAlignEngine()

    strider = PitcherSpinAlignMetrics(
        pitcher_id="p1",
        pitcher_name="Spencer Strider Archetype",
        spin_axis_std_dev_mins=10.0,
        release_height_std_dev_in=0.4,
        release_side_std_dev_in=0.5,
        pitch_arsenal_size=3,
    )

    res: SpinAlignEvaluationResult = engine.evaluate_spin_align(strider)

    assert res.asarci_score > 125.0
    assert res.deception_multiplier > 1.10
    assert res.alignment_tier == "MIRRORED_SPIN_TUNNEL_ILLUSIONIST"
    assert res.is_illusionist is True


def test_tipper_pitcher_triggers_tipping_tier():
    """Verify high axis and release std dev triggers TELEGRAPHED_ARM_SLOT_TIPPER."""
    engine = PitcherSpinAlignEngine()

    tipper = PitcherSpinAlignMetrics(
        pitcher_id="p2",
        pitcher_name="Arm Slot Tipper",
        spin_axis_std_dev_mins=45.0,
        release_height_std_dev_in=3.0,
        release_side_std_dev_in=2.8,
        pitch_arsenal_size=4,
    )

    res = engine.evaluate_spin_align(tipper)

    assert res.alignment_tier == "TELEGRAPHED_ARM_SLOT_TIPPER"
    assert res.is_illusionist is False


def test_spin_align_health_check():
    """Verify spin align health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Spin Align verified" in checks[0].detail
