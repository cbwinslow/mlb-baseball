"""Unit tests for Late-Inning Pinch-Hit & Substitution Simulator (SUB-01, ADR-141)."""

from mlb_baseball.model.sub import (
    BatterCard,
    TacticalSubstitutionEngine,
    health_check,
)


def test_late_inning_high_leverage_pinch_hit_recommendation():
    """Verify manager pinch-hits righty power bat vs lefty reliever in 8th inning."""
    engine = TacticalSubstitutionEngine()

    light_hitter = BatterCard(
        "b1", "Speedy Outfielder", bats="L", woba_vs_rhp=0.310, woba_vs_lhp=0.230
    )
    bench_slugger = BatterCard(
        "b2", "Righty Crusher", bats="R", woba_vs_rhp=0.320, woba_vs_lhp=0.380
    )

    rec = engine.evaluate_pinch_hit(
        current_batter=light_hitter,
        opposing_pitcher_hand="L",
        bench_players=[bench_slugger],
        inning=8,
        leverage_index=2.4,
    )

    assert rec.should_substitute is True
    assert rec.recommended_substitute_id == "b2"
    assert rec.recommended_substitute_name == "Righty Crusher"
    assert rec.expected_woba_gain == 0.150  # 0.380 - 0.230
    assert "Pinch-hit Righty Crusher" in rec.rationale


def test_early_inning_refuses_pinch_hit():
    """Verify manager does not burn bench player in 3rd inning."""
    engine = TacticalSubstitutionEngine()

    starter = BatterCard("b1", "Starter", bats="L", woba_vs_rhp=0.310, woba_vs_lhp=0.240)
    bench = BatterCard("b2", "Bench Bat", bats="R", woba_vs_rhp=0.320, woba_vs_lhp=0.350)

    rec = engine.evaluate_pinch_hit(
        current_batter=starter,
        opposing_pitcher_hand="L",
        bench_players=[bench],
        inning=3,  # Too early
        leverage_index=1.5,
    )

    assert rec.should_substitute is False
    assert rec.recommended_substitute_id is None


def test_sub_health_check():
    """Verify substitution health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Pinch hit verified" in checks[0].detail
