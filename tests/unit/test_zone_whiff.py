"""Unit tests for Batter In-Zone Whiff vs Contact Tradeoff Engine (ZONE-WHIFF-01, ADR-223)."""

from mlb_baseball.model.zone_whiff import (
    BatterZoneWhiffEngine,
    BatterZoneWhiffMetrics,
    health_check,
)


def test_zone_crusher_classified_as_elite_master():
    """Verify high zone barrel rate and sub-12% zone whiff yields ELITE_ZONE_CRUSHER_MASTER."""
    engine = BatterZoneWhiffEngine()

    alvarez = BatterZoneWhiffMetrics(
        batter_id="b1",
        batter_name="Yordan Alvarez Archetype",
        zone_swing_rate_pct=76.0,
        zone_whiff_rate_pct=9.5,
        zone_barrel_per_bbe_pct=19.0,
        zone_swings_count=450,
    )

    res = engine.evaluate_zone_whiff(alvarez)

    assert res.zcpoi_score > 125.0
    assert res.izpsr_runs_saved > 25.0
    assert res.tradeoff_tier == "ELITE_ZONE_CRUSHER_MASTER"
    assert res.is_elite_crusher is True


def test_slapper_triggers_empty_contact_tier():
    """Verify sub-7% zone whiff with sub-4% barrel rate triggers EMPTY_CONTACT_ZONE_SLAPPER."""
    engine = BatterZoneWhiffEngine()

    slapper = BatterZoneWhiffMetrics(
        batter_id="b2",
        batter_name="Zero Power Slapper",
        zone_swing_rate_pct=65.0,
        zone_whiff_rate_pct=5.5,
        zone_barrel_per_bbe_pct=3.0,
        zone_swings_count=310,
    )

    res = engine.evaluate_zone_whiff(slapper)

    assert res.tradeoff_tier == "EMPTY_CONTACT_ZONE_SLAPPER"
    assert res.is_elite_crusher is False


def test_zone_whiff_health_check():
    """Verify zone whiff health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Zone Whiff verified" in checks[0].detail
