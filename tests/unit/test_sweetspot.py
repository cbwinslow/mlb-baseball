"""Unit tests for Batter Sweet-Spot & Ideal Contact Rate Engine (SWEETSPOT-01, ADR-175)."""

from mlb_baseball.model.sweetspot import (
    BatterContactGeometry,
    SweetSpotEngine,
    health_check,
)


def test_line_drive_machine_hitter_classified_as_elite_striker():
    """Verify high ICR and Sweet-Spot% evaluates to LINE_DRIVE_MACHINE and elite striker."""
    engine = SweetSpotEngine()

    freeman = BatterContactGeometry(
        batter_id="b1",
        batter_name="Elite Line Drive Striker",
        sweet_spot_pct=0.43,
        hard_hit_pct=0.49,
        ideal_contact_rate=46.0,
        la_std_dev=19.5,
    )

    res = engine.evaluate_contact(freeman)

    assert res.ideal_contact_rate >= 45.0
    assert res.launch_path_archetype == "LINE_DRIVE_MACHINE"
    assert res.is_elite_ball_striker is True
    assert res.contact_quality_score > 40.0


def test_hard_hit_grounder_classified_properly():
    """Verify high hard hit rate with low sweet spot yields HARD_HIT_GROUNDER."""
    engine = SweetSpotEngine()

    grounder = BatterContactGeometry(
        batter_id="b2",
        batter_name="Top-Spin Grounder Hitter",
        sweet_spot_pct=0.24,
        hard_hit_pct=0.48,
        ideal_contact_rate=22.0,
        la_std_dev=26.0,
    )

    res = engine.evaluate_contact(grounder)

    assert res.launch_path_archetype == "HARD_HIT_GROUNDER"
    assert res.is_elite_ball_striker is False


def test_sweetspot_health_check():
    """Verify sweet spot health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Sweet-spot verified" in checks[0].detail
