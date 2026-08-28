"""Unit tests for Dynamic Bullpen Fatigue Simulator (BULLPEN-01, ADR-138)."""

from mlb_baseball.model.reliever import (
    AvailabilityStatus,
    BullpenWorkloadHierarchyEngine,
    RelieverProfile,
    RelieverRole,
    health_check,
)


def test_reliever_fatigue_and_availability_thresholds():
    """Verify 3-day pitch accumulation moves relievers from FRESH -> FATIGUED -> UNAVAILABLE."""
    engine = BullpenWorkloadHierarchyEngine()

    fresh_arm = RelieverProfile(
        "r1",
        "Fresh",
        RelieverRole.CLOSER,
        2.50,
        0.35,
        pitches_yesterday=0,
        pitches_2d_ago=0,
        pitches_3d_ago=15,
    )
    fatigued_arm = RelieverProfile(
        "r2", "Tired", RelieverRole.SETUP, 3.00, 0.30, pitches_yesterday=28, pitches_2d_ago=10
    )
    overworked_arm = RelieverProfile(
        "r3",
        "Cooked",
        RelieverRole.MIDDLE_RELIEF,
        3.50,
        0.25,
        pitches_yesterday=35,
        pitches_2d_ago=25,
    )

    s1 = engine.evaluate_reliever(fresh_arm)
    s2 = engine.evaluate_reliever(fatigued_arm)
    s3 = engine.evaluate_reliever(overworked_arm)

    assert s1.status == AvailabilityStatus.FRESH
    assert s1.effective_fip == 2.50
    assert s2.status == AvailabilityStatus.FATIGUED
    assert s2.effective_fip > 3.00
    assert s3.status == AvailabilityStatus.UNAVAILABLE
    assert s3.effective_fip > 4.50


def test_composite_team_bullpen_degradation():
    """Verify missing closer and setup arms degrades overall bullpen projected FIP."""
    engine = BullpenWorkloadHierarchyEngine()

    arms = [
        RelieverProfile(
            "r1",
            "Elite Closer",
            RelieverRole.CLOSER,
            true_talent_fip=2.20,
            true_talent_k_pct=0.38,
            pitches_yesterday=30,
            pitches_2d_ago=20,
        ),
        RelieverProfile(
            "r2",
            "Setup Arm",
            RelieverRole.SETUP,
            true_talent_fip=2.80,
            true_talent_k_pct=0.32,
            pitches_yesterday=30,
            pitches_2d_ago=20,
        ),
        RelieverProfile(
            "r3",
            "Long Relief",
            RelieverRole.LONG_RELIEF,
            true_talent_fip=4.50,
            true_talent_k_pct=0.20,
            pitches_yesterday=0,
            pitches_2d_ago=0,
        ),
    ]

    proj, states = engine.evaluate_bullpen("lad", "LAD", arms)

    assert proj.closer_status == AvailabilityStatus.UNAVAILABLE
    assert proj.setup_status == AvailabilityStatus.UNAVAILABLE
    assert proj.available_high_leverage_count == 0
    assert proj.expected_bullpen_fip_today == 4.50
    assert proj.fip_penalty_delta > 1.0


def test_reliever_health_check():
    """Verify reliever health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Bullpen fatigue verified" in checks[0].detail
