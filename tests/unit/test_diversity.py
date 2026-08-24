"""Unit tests for Pitcher Arsenal Diversity Engine (ARSENAL-01, ADR-169)."""

from mlb_baseball.model.diversity import (
    ArsenalDiversityEngine,
    DiversityArsenalMix,
    health_check,
)


def test_five_pitch_starter_classified_as_chameleon():
    """Verify 5-pitch balanced repertoire generates high Gini-Simpson ADI and entropy."""
    engine = ArsenalDiversityEngine()

    deep_mix = DiversityArsenalMix(
        pitcher_id="p1",
        pitcher_name="Deep Arsenal Starter",
        count_state="ALL_COUNTS",
        pitch_frequencies={"FF": 0.30, "SL": 0.25, "CH": 0.20, "CU": 0.15, "SI": 0.10},
    )

    res = engine.evaluate_diversity(deep_mix)

    assert res.pitch_count == 5
    assert res.diversity_index >= 0.90
    assert res.entropy_bits > 2.0
    assert res.repertoire_tier == "FIVE_PITCH_CHAMELEON"
    assert res.is_highly_predictable is False


def test_two_pitch_reliever_triggers_predictability_flag():
    """Verify 2-pitch reliever over-relying on primary pitch is flagged as predictable."""
    engine = ArsenalDiversityEngine()

    predictable = DiversityArsenalMix(
        pitcher_id="p2",
        pitcher_name="Fastball Heavy Reliever",
        count_state="TWO_STRIKES",
        pitch_frequencies={"FF": 0.78, "SL": 0.22},
    )

    res = engine.evaluate_diversity(predictable)

    assert res.pitch_count == 2
    assert res.repertoire_tier == "TWO_PITCH_PREDICTABLE"
    assert res.is_highly_predictable is True


def test_diversity_health_check():
    """Verify diversity health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Diversity verified" in checks[0].detail
