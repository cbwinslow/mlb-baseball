"""Unit tests for Pitch Sequencing Entropy Engine (ENTROPY-01, ADR-144)."""

from mlb_baseball.model.entropy import (
    PitchArsenalDistribution,
    PitchSequencingEntropyEngine,
    health_check,
)


def test_four_pitch_equal_mix_reaches_maximum_entropy():
    """Verify 4 pitches thrown at equal 25% frequency has normalized entropy = 1.0."""
    engine = PitchSequencingEntropyEngine()

    arsenal = PitchArsenalDistribution(
        pitcher_id="p1",
        pitcher_name="Max Entropy Ace",
        pitch_shares={"FF": 0.25, "SL": 0.25, "CH": 0.25, "CU": 0.25},
    )

    res = engine.evaluate_arsenal_entropy(arsenal)

    assert res.shannon_entropy_bits == 2.0  # log2(4) = 2.0
    assert res.normalized_entropy == 1.000
    assert res.predictability_score == 0.0


def test_heavily_skewed_arsenal_is_highly_predictable():
    """Verify 90% fastball reliever is highly predictable with elevated contact penalty."""
    engine = PitchSequencingEntropyEngine()

    arsenal = PitchArsenalDistribution(
        pitcher_id="p2",
        pitcher_name="Fastball Only",
        pitch_shares={"FF": 0.90, "SL": 0.10},
    )

    res = engine.evaluate_arsenal_entropy(arsenal)

    assert res.normalized_entropy < 0.50
    assert res.predictability_score > 50.0
    assert res.repetition_contact_penalty_pct > 10.0


def test_entropy_health_check():
    """Verify entropy health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Entropy verified" in checks[0].detail
