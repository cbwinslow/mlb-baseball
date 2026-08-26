"""Unit tests for Pitcher Extension Engine (EXT-01, ADR-153)."""

from mlb_baseball.model.extension import (
    PitcherExtensionEngine,
    PitcherExtensionProfile,
    health_check,
)


def test_elite_extension_increases_perceived_velocity():
    """Verify long stride (>7.0 ft) reduces time-to-plate and boosts perceived velocity."""
    engine = PitcherExtensionEngine()

    glasnow = PitcherExtensionProfile(
        pitcher_id="p1",
        pitcher_name="Elite Extension Pitcher",
        release_extension_ft=7.4,
        radar_velocity_mph=96.0,
    )

    res = engine.evaluate_effective_velocity(glasnow)

    assert res.extension_tier == "ELITE_LONG"
    # EXT-01 fix: the velocity-boost formula now anchors at 6.2 ft (the field's own
    # documented MLB average) instead of 6.0 ft, so a 7.4 ft extension now produces
    # exactly +1.5 mph / 97.5 mph rather than the old (buggy) +1.75 mph / 97.75 mph.
    assert res.velocity_delta_mph > 1.2
    assert res.perceived_velocity_mph > 97.0
    assert res.time_to_plate_ms < 400.0


def test_short_extension_decreases_perceived_velocity():
    """Verify short stride (<5.8 ft) gives batters more optical reaction time."""
    engine = PitcherExtensionEngine()

    short_stride = PitcherExtensionProfile(
        pitcher_id="p2",
        pitcher_name="Short Stride Pitcher",
        release_extension_ft=5.5,
        radar_velocity_mph=94.0,
    )

    res = engine.evaluate_effective_velocity(short_stride)

    assert res.extension_tier == "SHORT_COMPACT"
    assert res.velocity_delta_mph < 0.0
    assert res.perceived_velocity_mph < 94.0


def test_default_extension_produces_neutral_velocity_delta():
    """EXT-01 regression: the field default (release_extension_ft=6.2) is documented as
    the MLB average. Feeding the engine its own default should now produce exactly zero
    velocity delta (no boost, no penalty) instead of the +0.25 mph the old 6.0 ft anchor
    incorrectly produced for a league-average pitcher.
    """
    engine = PitcherExtensionEngine()
    average_pitcher = PitcherExtensionProfile(pitcher_id="p3", pitcher_name="League Average")

    res = engine.evaluate_effective_velocity(average_pitcher)

    assert res.velocity_delta_mph == 0.0
    assert res.perceived_velocity_mph == average_pitcher.radar_velocity_mph


def test_extension_health_check():
    """Verify extension health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Extension verified" in checks[0].detail
