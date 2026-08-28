"""Unit tests for Batter Two-Strike Expansion Resistance Engine (EXP-RESIST-01, ADR-208)."""

from mlb_baseball.model.exp_resist import (
    BatterExpansionResistanceEngine,
    BatterExpansionResistanceMetrics,
    health_check,
)


def test_contact_battler_classified_as_elite_resistor():
    """Verify low chase and high O-contact yields ELITE_ZONE_EXPANSION_RESISTOR."""
    engine = BatterExpansionResistanceEngine()

    kwan = BatterExpansionResistanceMetrics(
        batter_id="b1",
        batter_name="Steven Kwan Archetype",
        two_strike_chase_pct=20.0,
        two_strike_o_contact_pct=75.0,
        two_strike_foul_pct=52.0,
        two_strike_pa_count=320,
    )

    res = engine.evaluate_resistance(kwan)

    assert res.teri_score > 125.0
    assert res.runs_value > 20.0
    assert res.resistance_tier == "ELITE_ZONE_EXPANSION_RESISTOR"
    assert res.is_elite_resistor is True


def test_free_swinger_triggers_chase_victim_tier():
    """Verify high chase rate triggers CHASE_PRONE_TWO_STRIKE_VICTIM."""
    engine = BatterExpansionResistanceEngine()

    chaser = BatterExpansionResistanceMetrics(
        batter_id="b2",
        batter_name="Free Swinger",
        two_strike_chase_pct=46.0,
        two_strike_o_contact_pct=45.0,
        two_strike_foul_pct=34.0,
        two_strike_pa_count=200,
    )

    res = engine.evaluate_resistance(chaser)

    assert res.resistance_tier == "CHASE_PRONE_TWO_STRIKE_VICTIM"
    assert res.is_elite_resistor is False


def test_exp_resist_health_check():
    """Verify expansion resistance health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Exp Resist verified" in checks[0].detail
