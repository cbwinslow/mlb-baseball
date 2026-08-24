"""Unit tests for Pitch Count Markov Engine (COUNT-01, ADR-139)."""

import numpy as np

from mlb_baseball.model.count import (
    CountState,
    PitchCountMarkovEngine,
    PitchOutcome,
    TerminalPAOutcome,
    health_check,
)


def test_count_state_properties():
    """Verify count state classifications (hitter vs pitcher counts)."""
    c00 = CountState(0, 0)
    c02 = CountState(0, 2)
    c30 = CountState(3, 0)
    c12 = CountState(1, 2)
    c31 = CountState(3, 1)

    assert c00.is_hitter_count is False
    assert c00.is_pitcher_count is False
    assert c02.is_pitcher_count is True
    assert c12.is_pitcher_count is True
    assert c30.is_hitter_count is True
    assert c31.is_hitter_count is True


def test_pitch_probabilities_shift_by_count():
    """Verify swinging strike probability increases in 0-2 vs 3-0."""
    engine = PitchCountMarkovEngine()

    p_02 = engine.get_pitch_probabilities(CountState(0, 2), whiff_base_rate=0.25)
    p_30 = engine.get_pitch_probabilities(CountState(3, 0), whiff_base_rate=0.25)

    assert p_02[PitchOutcome.SWINGING_STRIKE] > p_30[PitchOutcome.SWINGING_STRIKE]
    assert p_30[PitchOutcome.CALLED_STRIKE] > p_02[PitchOutcome.CALLED_STRIKE]


def test_deterministic_plate_appearance_simulation():
    """Verify plate appearance simulation terminates in valid absorbing outcome."""
    engine = PitchCountMarkovEngine()
    rng = np.random.default_rng(123)

    res = engine.simulate_plate_appearance(0, 0, rng=rng)

    assert res.total_pitches >= 1
    assert res.terminal_outcome in (
        TerminalPAOutcome.STRIKEOUT,
        TerminalPAOutcome.WALK,
        TerminalPAOutcome.BALL_IN_PLAY,
        TerminalPAOutcome.HIT_BY_PITCH,
    )
    assert res.count_history[0] == "0-0"


def test_count_health_check():
    """Verify count health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Count Markov verified" in checks[0].detail
