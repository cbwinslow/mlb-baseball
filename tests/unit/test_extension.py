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
    assert res.velocity_delta_mph > 1.5
    assert res.perceived_velocity_mph > 97.5
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


def test_extension_health_check():
    """Verify extension health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Extension verified" in checks[0].detail
