"""Unit tests for Batter In-Zone Whiff vs Chase Engine (ZONE-SWING-01, ADR-171)."""

from mlb_baseball.model.zone_swing import (
    BatterZoneSwingMetrics,
    ZoneSwingVulnerabilityEngine,
    health_check,
)


def test_elite_discipline_hitter_classified_as_in_zone_punisher():
    """Verify high in-zone contact and low chase rate evaluates to IN_ZONE_PUNISHER."""
    engine = ZoneSwingVulnerabilityEngine()

    soto = BatterZoneSwingMetrics(
        batter_id="b1",
        batter_name="Disciplined Slugger",
        z_swing_pct=0.67,
        z_contact_pct=0.89,
        o_swing_pct=0.19,
        o_contact_pct=0.68,
    )

    res = engine.evaluate_discipline(soto, league_z_contact=0.820)

    assert res.zone_contact_deficit < -0.050
    assert res.chase_efficiency_ratio < 0.35
    assert res.vulnerability_archetype == "IN_ZONE_PUNISHER"
    assert res.is_exploitable_whiff_target is False


def test_free_swinger_classified_as_chase_vulnerable():
    """Verify high chase rate triggers CHASE_VULNERABLE and exploitable flag."""
    engine = ZoneSwingVulnerabilityEngine()

    hacker = BatterZoneSwingMetrics(
        batter_id="b2",
        batter_name="Aggressive Hacker",
        z_swing_pct=0.74,
        z_contact_pct=0.76,
        o_swing_pct=0.44,
        o_contact_pct=0.48,
    )

    res = engine.evaluate_discipline(hacker, league_z_contact=0.820)

    assert res.chase_efficiency_ratio > 0.50
    assert res.vulnerability_archetype == "CHASE_VULNERABLE"
    assert res.is_exploitable_whiff_target is True


def test_zone_swing_health_check():
    """Verify zone swing health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Discipline verified" in checks[0].detail
