import random

import pytest

from mlb_baseball.model.markov import (
    TERMINAL,
    BaseOutState,
    MarkovError,
    Outcome,
    TransitionCountRow,
    build_outcome_distribution,
    simulate_half_inning,
    simulate_half_innings,
    summarize_runs,
)


def test_build_outcome_distribution_keeps_runs_scored_per_transition():
    # Two rows share the same (pre, post) pair but different runs_scored --
    # build_transition_matrix would merge these into one post-state bucket
    # and lose which count went with which run total. build_outcome_distribution
    # must keep them as two distinct, separately-weighted outcomes, since
    # "which state we end up in" and "how many runs scored getting there"
    # are correlated, not independent -- sampling them separately from
    # marginal distributions would produce game states that never actually
    # co-occurred in the real data.
    pre = BaseOutState(0, True, True, True)  # loaded, 0 outs
    post = BaseOutState(1, False, True, True)  # 2nd+3rd, 1 out
    rows = [
        # 3 plays: fielder's choice, no one scores.
        TransitionCountRow(0, True, True, True, 1, False, True, True, 0, 3),
        # 1 play: a single scores the runner from 3rd too.
        TransitionCountRow(0, True, True, True, 1, False, True, True, 1, 1),
    ]
    distribution = build_outcome_distribution(rows)
    outcomes = distribution[pre]
    assert outcomes[Outcome(post, 0)] == pytest.approx(0.75)
    assert outcomes[Outcome(post, 1)] == pytest.approx(0.25)
    assert sum(outcomes.values()) == pytest.approx(1.0)


def test_build_outcome_distribution_validates_rows():
    rows = [TransitionCountRow(0, False, False, False, 0, True, False, False, 0, 0)]
    with pytest.raises(MarkovError, match="non-positive row count"):
        build_outcome_distribution(rows)


def test_simulate_half_inning_walks_a_deterministic_chain():
    # A -> B (0 runs, certain) -> TERMINAL (2 runs, certain). No actual
    # randomness involved (single-outcome distributions at every step), so
    # this proves the walk-and-sum logic itself, independent of sampling.
    empty_zero = BaseOutState(0, False, False, False)
    first_zero = BaseOutState(0, True, False, False)
    distribution = {
        empty_zero: {Outcome(first_zero, 0): 1.0},
        first_zero: {Outcome(TERMINAL, 2): 1.0},
    }
    runs = simulate_half_inning(distribution, random.Random(0))
    assert runs == 2


def test_simulate_half_inning_is_deterministic_for_a_fixed_seed():
    empty_zero = BaseOutState(0, False, False, False)
    first_zero = BaseOutState(0, True, False, False)
    distribution = {
        empty_zero: {
            Outcome(first_zero, 0): 0.5,
            Outcome(TERMINAL, 0): 0.5,
        },
        first_zero: {Outcome(TERMINAL, 1): 1.0},
    }
    first = simulate_half_inning(distribution, random.Random(42))
    second = simulate_half_inning(distribution, random.Random(42))
    assert first == second


def test_simulate_half_inning_raises_on_a_dead_end_state():
    # A state with no observed outcomes at all (e.g. estimated from a
    # narrow real sample that never saw this configuration) must fail
    # loudly, not silently hang or return a nonsensical result.
    empty_zero = BaseOutState(0, False, False, False)
    distribution: dict[BaseOutState, dict[Outcome, float]] = {}
    with pytest.raises(MarkovError, match="no observed outcomes"):
        simulate_half_inning(distribution, random.Random(0), start=empty_zero)


def test_simulate_half_innings_sampling_converges_to_the_true_expected_value():
    # Law-of-large-numbers regression check, not a hand-picked exact value:
    # a 50/50 split between 0 runs and 4 runs has a true expected value of
    # 2.0. Over many trials with a fixed seed, the sample mean must land
    # close to that -- a real proof the weighted sampling actually reflects
    # the input probabilities, not just that it runs without error.
    empty_zero = BaseOutState(0, False, False, False)
    distribution = {
        empty_zero: {
            Outcome(TERMINAL, 0): 0.5,
            Outcome(TERMINAL, 4): 0.5,
        },
    }
    results = simulate_half_innings(distribution, random.Random(7), 20_000)
    mean = sum(results) / len(results)
    assert mean == pytest.approx(2.0, abs=0.1)


def test_simulate_half_innings_returns_one_result_per_requested_inning():
    empty_zero = BaseOutState(0, False, False, False)
    distribution = {empty_zero: {Outcome(TERMINAL, 0): 1.0}}
    results = simulate_half_innings(distribution, random.Random(0), 5)
    assert len(results) == 5
    assert all(r == 0 for r in results)


def test_summarize_runs_matches_hand_calculation():
    # 9 values: median is the 5th (index 4) of the sorted list; p90 is the
    # ceil(0.9*9)=9th value (index 8), i.e. the max itself here.
    values = [0, 0, 1, 1, 1, 2, 3, 4, 7]
    summary = summarize_runs(values)
    assert summary["count"] == 9
    assert summary["mean"] == pytest.approx(sum(values) / 9)
    assert summary["median"] == 1
    assert summary["max"] == 7


def test_summarize_runs_rejects_empty_input():
    with pytest.raises(MarkovError, match="empty"):
        summarize_runs([])
