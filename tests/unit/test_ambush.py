"""Unit tests for Batter First-Pitch Ambush Engine (AMBUSH-01, ADR-205)."""

from mlb_baseball.model.ambush import (
    BatterAmbushEngine,
    BatterAmbushMetrics,
    health_check,
)


def test_first_pitch_crusher_classified_as_lethal_ambusher():
    """Verify aggressive in-zone swing rate and high 0-0 SLG yields LETHAL_FIRST_PITCH_AMBUSHER."""
    engine = BatterAmbushEngine()

    seager = BatterAmbushMetrics(
        batter_id="b1",
        batter_name="Corey Seager Archetype",
        first_pitch_swing_pct=45.0,
        first_pitch_zone_swing_pct=72.0,
        first_pitch_chase_pct=11.0,
        first_pitch_hard_hit_pct=60.0,
        first_pitch_slugging=0.890,
        first_pitch_pa_count=600,
    )

    res = engine.evaluate_ambush(seager)

    assert res.fpav_score > 125.0
    assert res.fpsv_runs_saved > 10.0
    assert res.ambush_tier == "LETHAL_FIRST_PITCH_AMBUSHER"
    assert res.is_lethal_ambusher is True


def test_passive_taker_triggers_passive_tier():
    """Verify low first pitch swing rate triggers PASSIVE_FIRST_PITCH_TAKER."""
    engine = BatterAmbushEngine()

    passive = BatterAmbushMetrics(
        batter_id="b2",
        batter_name="Passive 0-0 Taker",
        first_pitch_swing_pct=12.0,
        first_pitch_zone_swing_pct=26.0,
        first_pitch_chase_pct=6.0,
        first_pitch_hard_hit_pct=34.0,
        first_pitch_slugging=0.450,
        first_pitch_pa_count=520,
    )

    res = engine.evaluate_ambush(passive)

    assert res.ambush_tier == "PASSIVE_FIRST_PITCH_TAKER"
    assert res.is_lethal_ambusher is False


def test_ambush_health_check():
    """Verify ambush health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Ambush verified" in checks[0].detail
