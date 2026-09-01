"""Hand-calculated Empirical Bayes shrink for matchup outcome distributions.

Layer 2 of the prediction ladder (ADR-271): mix a sparse matchup sample
toward the league-average 24-state distribution with M=350 PA
(Tango / The Book). Pure logic — no database.
"""

import random

import pytest

from mlb_baseball.model.markov import (
    MATCHUP_PRIOR_PA,
    TERMINAL,
    BaseOutState,
    MarkovError,
    Outcome,
    shrink_outcome_distribution,
    simulate_game,
    simulate_home_win_rate,
)

EMPTY_ZERO = BaseOutState(0, False, False, False)


def test_shrink_n_zero_returns_the_league_distribution():
    league = {EMPTY_ZERO: {Outcome(TERMINAL, 0): 1.0}}
    raw = {EMPTY_ZERO: {Outcome(TERMINAL, 1): 1.0}}
    out = shrink_outcome_distribution(raw, league, n=0, m=350)
    assert out[EMPTY_ZERO][Outcome(TERMINAL, 0)] == pytest.approx(1.0)
    assert Outcome(TERMINAL, 1) not in out[EMPTY_ZERO]


def test_shrink_equal_sample_and_prior_is_an_even_mix():
    # n = M = 350 → weight 1/2. League always scores 0 on the only play;
    # raw always scores 1. Mixed P(0) = P(1) = 0.5.
    league = {EMPTY_ZERO: {Outcome(TERMINAL, 0): 1.0}}
    raw = {EMPTY_ZERO: {Outcome(TERMINAL, 1): 1.0}}
    out = shrink_outcome_distribution(raw, league, n=350, m=350)
    outcomes = out[EMPTY_ZERO]
    assert outcomes[Outcome(TERMINAL, 0)] == pytest.approx(0.5)
    assert outcomes[Outcome(TERMINAL, 1)] == pytest.approx(0.5)


def test_shrink_fifty_pa_is_one_eighth_raw():
    # n=50, M=350 → w = 50/400 = 0.125. Hand: 0.125 * raw + 0.875 * league.
    league = {EMPTY_ZERO: {Outcome(TERMINAL, 0): 1.0}}
    raw = {EMPTY_ZERO: {Outcome(TERMINAL, 1): 1.0}}
    out = shrink_outcome_distribution(raw, league, n=50, m=MATCHUP_PRIOR_PA)
    outcomes = out[EMPTY_ZERO]
    assert outcomes[Outcome(TERMINAL, 1)] == pytest.approx(0.125)
    assert outcomes[Outcome(TERMINAL, 0)] == pytest.approx(0.875)


def test_shrink_missing_raw_state_copies_league():
    first_zero = BaseOutState(0, True, False, False)
    league = {
        EMPTY_ZERO: {Outcome(TERMINAL, 0): 1.0},
        first_zero: {Outcome(TERMINAL, 1): 1.0},
    }
    raw = {EMPTY_ZERO: {Outcome(TERMINAL, 0): 1.0}}
    out = shrink_outcome_distribution(raw, league, n=50, m=350)
    assert out[first_zero][Outcome(TERMINAL, 1)] == pytest.approx(1.0)


def test_shrink_rejects_negative_n_or_nonpositive_m():
    league = {EMPTY_ZERO: {Outcome(TERMINAL, 0): 1.0}}
    with pytest.raises(MarkovError, match="n must be"):
        shrink_outcome_distribution({}, league, n=-1, m=350)
    with pytest.raises(MarkovError, match="m must be"):
        shrink_outcome_distribution({}, league, n=10, m=0)


def test_simulate_home_win_rate_still_fails_loud_on_an_unbreakable_tie():
    # Both sides always score exactly 0 -- every game is an eternal tie
    # no sampled path can break. The Monte Carlo path (max_innings now
    # defaults to 100, up from 30) must still raise MarkovError on a
    # genuinely degenerate distribution, not silently coin-flip its way
    # to a win rate.
    tie = {EMPTY_ZERO: {Outcome(TERMINAL, 0): 1.0}}
    with pytest.raises(MarkovError, match="innings"):
        simulate_home_win_rate(tie, tie, random.Random(0), n_games=1)


def test_lopsided_home_distribution_wins_every_simulated_game():
    # Away never scores (one play, 3 outs, 0 runs). Home always scores 1
    # the same way. simulate_game must then record a home win every trial.
    away = {EMPTY_ZERO: {Outcome(TERMINAL, 0): 1.0}}
    home = {EMPTY_ZERO: {Outcome(TERMINAL, 1): 1.0}}
    rate = simulate_home_win_rate(
        away, home, random.Random(0), n_games=25, regulation_innings=2, max_innings=4
    )
    assert rate == 1.0
    result = simulate_game(
        away, random.Random(1), regulation_innings=2, max_innings=4, home_distribution=home
    )
    assert result.home_runs > result.away_runs
