"""Unit tests for Batter Swing Decision Engine (DECISION-01, ADR-151)."""

from mlb_baseball.model.decision import (
    BatterSwingDecisionEngine,
    BatterZoneRates,
    DisciplineArchetype,
    health_check,
)


def test_disciplined_slugger_generates_positive_run_value():
    """Verify high heart swing and low chase produces elite SDV and positive run value."""
    engine = BatterSwingDecisionEngine()

    soto_profile = BatterZoneRates(
        batter_id="b1",
        batter_name="Disciplined Slugger",
        heart_swing_pct=0.78,
        shadow_swing_pct=0.50,
        chase_swing_pct=0.18,
        waste_swing_pct=0.04,
    )

    res = engine.evaluate_batter_discipline(soto_profile)

    assert res.archetype == DisciplineArchetype.DISCIPLINED_SLUGGER
    assert res.discipline_grade == "ELITE"
    assert res.swing_decision_val_per_100 > 0.70
    assert res.season_run_value_added > 15.0


def test_vulnerable_chaser_generates_negative_run_value():
    """Verify excessive chase rates produce negative run value and vulnerable tier."""
    engine = BatterSwingDecisionEngine()

    baez_profile = BatterZoneRates(
        batter_id="b2",
        batter_name="Aggressive Chaser",
        heart_swing_pct=0.82,
        shadow_swing_pct=0.62,
        chase_swing_pct=0.40,
        waste_swing_pct=0.15,
    )

    res = engine.evaluate_batter_discipline(baez_profile)

    assert res.archetype == DisciplineArchetype.VULNERABLE_CHASER
    assert res.discipline_grade == "POOR"
    assert res.swing_decision_val_per_100 < -0.15
    assert res.season_run_value_added < -5.0


def test_decision_health_check():
    """Verify decision health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Decision verified" in checks[0].detail
