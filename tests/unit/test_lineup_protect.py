"""Tests for Batter Lineup Protection & On-Deck Advantage Engine (LINEUP-PROTECT-01)."""

from mlb_baseball.model.lineup_protect import (
    BatterLineupProtectionEngine,
    BatterProtectionMetrics,
    ProtectionEvaluationResult,
    health_check,
)


def test_elite_protection_classified_properly():
    """Verify high on-deck woba with good zone% yields ELITE protection."""
    engine = BatterLineupProtectionEngine()

    soto = BatterProtectionMetrics(
        batter_id="p1",
        batter_name="Juan Soto Archetype",
        on_deck_woba=0.410,
        zone_pct=54.0,
        first_pitch_strike_pct=70.0,
        pa_count=250,
        intentional_walk_pct=0.8,
    )

    res: ProtectionEvaluationResult = engine.evaluate_protection(soto)

    assert res.pii_score > 115.0
    assert res.lprv_runs > 3.0
    assert res.protection_tier == "ELITE_ON_DECK_PROTECTION_SHIELD"
    assert res.is_heavily_protected is True


def test_unprotected_liability_tier():
    """Verify low on-deck woba yields UNPROTECTED liability tier."""
    engine = BatterLineupProtectionEngine()

    weak = BatterProtectionMetrics(
        batter_id="p2",
        batter_name="Weak 9-Hole Follower",
        on_deck_woba=0.230,
        zone_pct=35.0,
        first_pitch_strike_pct=48.0,
        pa_count=100,
    )

    res: ProtectionEvaluationResult = engine.evaluate_protection(weak)

    assert res.pii_score < 100.0
    assert res.lprv_runs < 0.0
    assert res.protection_tier == "UNPROTECTED_NIBBLE_TARGET_LIABILITY"
    assert res.is_heavily_protected is False


def test_lineup_protect_health_check():
    """Verify lineup protection health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
