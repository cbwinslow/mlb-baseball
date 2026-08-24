"""Unit tests for Pitcher Extension Perceived Velocity Engine (EXT-PERCEIVE-01, ADR-215)."""

from mlb_baseball.model.ext_perceive import (
    ExtPerceiveEvaluationResult,
    PitcherExtensionKinematicsMetrics,
    PitcherExtPerceiveEngine,
    health_check,
)


def test_long_extension_pitcher_classified_as_elite_deceiver():
    """Verify 7.2+ ft extension yields velocity boost and ELITE_LONG_EXTENSION_DECEIVER."""
    engine = PitcherExtPerceiveEngine()

    gilbert = PitcherExtensionKinematicsMetrics(
        pitcher_id="p1",
        pitcher_name="Logan Gilbert Archetype",
        extension_ft=7.35,
        radar_velocity_mph=96.0,
        induced_vert_break_in=18.5,
        release_z_ft=5.75,
        pitch_count_evaluated=250,
    )

    res: ExtPerceiveEvaluationResult = engine.evaluate_extension(gilbert)

    assert res.effective_velocity_mph > 96.90
    assert res.reaction_time_compression_ms > 6.0
    assert res.ever_score > 125.0
    assert res.whiff_boost_multiplier > 1.08
    assert res.extension_tier == "ELITE_LONG_EXTENSION_DECEIVER"
    assert res.is_elite_deceiver is True


def test_compact_short_extension_triggers_penalized_tier():
    """Verify short sub-5.7ft extension triggers COMPACT_SHORT_EXTENSION_PENALIZED."""
    engine = PitcherExtPerceiveEngine()

    short_ext = PitcherExtensionKinematicsMetrics(
        pitcher_id="p2",
        pitcher_name="Short Arm Delivery",
        extension_ft=5.60,
        radar_velocity_mph=92.5,
        induced_vert_break_in=14.0,
        release_z_ft=6.10,
        pitch_count_evaluated=190,
    )

    res = engine.evaluate_extension(short_ext)

    assert res.extension_tier == "COMPACT_SHORT_EXTENSION_PENALIZED"
    assert res.is_elite_deceiver is False


def test_ext_perceive_health_check():
    """Verify extension perceived velocity health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Ext Perceive verified" in checks[0].detail
