"""Unit tests for Pitcher Top-of-Zone VAA Deception Engine (VAA-TOZ-01, ADR-204)."""

from mlb_baseball.model.vaa_toz import (
    PitcherTOZVAAEngine,
    PitcherTOZVAAMetrics,
    health_check,
)


def test_flat_rising_fastball_evaluates_as_deadly_flat():
    """Verify low release and high IVB yields flat VAA and DEADLY_FLAT_RISING_HEATER tier."""
    engine = PitcherTOZVAAEngine()

    strider = PitcherTOZVAAMetrics(
        pitcher_id="p1",
        pitcher_name="Spencer Strider Archetype",
        pitch_type="FF",
        release_z_ft=5.3,
        release_velo_mph=98.5,
        induced_vert_break_in=20.5,
        plate_crossing_z_ft=3.4,
        extension_ft=7.1,
    )

    res = engine.evaluate_toz_vaa(strider)

    assert res.vaa_toz_deg >= -4.20
    assert res.toz_flatness_index > 120.0
    assert res.whiff_boost_multiplier > 1.08
    assert res.vaa_tier == "DEADLY_FLAT_RISING_HEATER"
    assert res.is_deadly_flat_heater is True


def test_steep_downhill_fastball_triggers_steep_tier():
    """Verify high release and low IVB triggers STEEP_DOWNHILL_FASTBALL tier."""
    engine = PitcherTOZVAAEngine()

    tall_p = PitcherTOZVAAMetrics(
        pitcher_id="p2",
        pitcher_name="Steep Release Pitcher",
        pitch_type="FF",
        release_z_ft=6.8,
        release_velo_mph=91.0,
        induced_vert_break_in=12.0,
        plate_crossing_z_ft=3.4,
        extension_ft=5.8,
    )

    res = engine.evaluate_toz_vaa(tall_p)

    assert res.vaa_toz_deg <= -5.80
    assert res.vaa_tier == "STEEP_DOWNHILL_FASTBALL"
    assert res.is_deadly_flat_heater is False


def test_vaa_toz_health_check():
    """Verify VAA TOZ health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "VAA TOZ verified" in checks[0].detail
