"""Unit tests for Batter Contact Quality & Damage Rate Engine (DAMAGE-01, ADR-159)."""

from mlb_baseball.model.damage import (
    BattedBallContact,
    BatterContactProfile,
    ContactDamageEngine,
    health_check,
)


def test_elite_barrel_hitter_classified_as_elite_slugger():
    """Verify high exit velocity in sweet spot launch window generates high damage rate."""
    engine = ContactDamageEngine()

    contacts = [
        BattedBallContact("c1", 107.5, 27.0),
        BattedBallContact("c2", 105.0, 24.0),
        BattedBallContact("c3", 102.0, 30.0),
        BattedBallContact("c4", 96.0, 15.0),
        BattedBallContact("c5", 85.0, 10.0),
    ]
    profile = BatterContactProfile("b1", "Aaron Judge Archetype", contacts)
    res = engine.evaluate_damage(profile)

    assert res.total_bbe == 5
    assert res.barrel_count == 3
    assert res.damage_rate_pct >= 60.0
    assert res.damage_tier == "ELITE_SLUGGER"
    assert res.expected_damage_value > 0.80


def test_contact_slap_hitter_low_damage_rate():
    """Verify ground-ball slap hitter produces low damage tier."""
    engine = ContactDamageEngine()

    contacts = [
        BattedBallContact("c1", 82.0, -4.0),
        BattedBallContact("c2", 78.0, 8.0),
        BattedBallContact("c3", 89.0, 12.0),
        BattedBallContact("c4", 75.0, -10.0),
        BattedBallContact("c5", 68.0, 50.0),
    ]
    profile = BatterContactProfile("b2", "Slap Hitter", contacts)
    res = engine.evaluate_damage(profile)

    assert res.barrel_count == 0
    assert res.damage_rate_pct < 10.0
    assert res.damage_tier == "CONTACT_SLAP_HITTER"


def test_damage_health_check():
    """Verify damage health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Damage verified" in checks[0].detail
