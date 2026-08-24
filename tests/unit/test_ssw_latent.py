"""Unit tests for Pitcher Seam-Shifted Wake Latent Movement Engine (SSW-LATENT-01, ADR-232)."""

from mlb_baseball.model.ssw_latent import (
    PitcherSswLatentEngine,
    PitcherSswLatentMetrics,
    SswLatentEvaluationResult,
    health_check,
)


def test_ssw_manipulator_classified_properly():
    """Verify 4+ inches latent break yields ELITE_SEAM_SHIFTED_WAKE_MANIPULATOR."""
    engine = PitcherSswLatentEngine()

    webb = PitcherSswLatentMetrics(
        pitcher_id="p1",
        pitcher_name="Logan Webb Archetype",
        pitch_type="Sinker",
        optical_axis_minutes=75,
        inferred_axis_minutes=130,
        observed_break_in=20.0,
        pure_magnus_break_in=14.5,
        pitch_count_evaluated=280,
    )

    res: SswLatentEvaluationResult = engine.evaluate_ssw(webb)

    assert res.axis_deviation_mins == 55
    assert res.latent_ssw_break_in > 5.0
    assert res.sswlmr_score > 125.0
    assert res.ssw_tier == "ELITE_SEAM_SHIFTED_WAKE_MANIPULATOR"
    assert res.is_elite_manipulator is True


def test_symmetrical_pitcher_triggers_pure_magnus_tier():
    """Verify minimal latent break triggers PURE_SYMMETRICAL_MAGNUS_DELIVERY."""
    engine = PitcherSswLatentEngine()

    pure_magnus = PitcherSswLatentMetrics(
        pitcher_id="p2",
        pitcher_name="Pure Fastballer",
        pitch_type="4-Seam",
        optical_axis_minutes=60,
        inferred_axis_minutes=65,
        observed_break_in=16.0,
        pure_magnus_break_in=15.8,
        pitch_count_evaluated=200,
    )

    res = engine.evaluate_ssw(pure_magnus)

    assert res.ssw_tier == "PURE_SYMMETRICAL_MAGNUS_DELIVERY"
    assert res.is_elite_manipulator is False


def test_ssw_latent_health_check():
    """Verify ssw latent health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "SSW Latent verified" in checks[0].detail
