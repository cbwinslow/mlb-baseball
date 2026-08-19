import pytest

from mlb_baseball.model import markov
from mlb_baseball.model.markov import (
    TERMINAL,
    BaseOutState,
    MarkovError,
    TransitionCountRow,
    build_transition_matrix,
    run_expectancy,
)


def test_basic_two_state_aggregation_produces_correct_probabilities():
    # From bases-empty/0-outs: 3 singles (-> 1st/0-outs) and 1 strikeout
    # (-> bases-empty/1-out). Hand-computed: 3/4 = 0.75, 1/4 = 0.25.
    rows = [
        TransitionCountRow(0, False, False, False, 0, True, False, False, 0, 3),
        TransitionCountRow(0, False, False, False, 1, False, False, False, 0, 1),
    ]
    matrix = build_transition_matrix(rows)
    pre = BaseOutState(0, False, False, False)
    assert matrix[pre][BaseOutState(0, True, False, False)] == pytest.approx(0.75)
    assert matrix[pre][BaseOutState(1, False, False, False)] == pytest.approx(0.25)


def test_probabilities_sum_to_one_for_every_pre_state():
    rows = [
        TransitionCountRow(0, False, False, False, 0, True, False, False, 0, 7),
        TransitionCountRow(0, False, False, False, 1, False, False, False, 0, 13),
        TransitionCountRow(1, True, False, False, 2, False, True, False, 0, 4),
        TransitionCountRow(1, True, False, False, 3, False, False, False, 0, 6),
    ]
    matrix = build_transition_matrix(rows)
    for post_probs in matrix.values():
        assert sum(post_probs.values()) == pytest.approx(1.0)


def test_terminal_states_collapse_regardless_of_base_flags():
    # A third out with a runner still on base (post_b1=True) and a third
    # out with the bases empty (post_b1=False) are both "half-inning over"
    # -- base occupancy is meaningless once outs=3, so both must merge
    # into the single TERMINAL post-state, not stay split.
    rows = [
        TransitionCountRow(2, True, False, False, 3, True, False, False, 0, 5),
        TransitionCountRow(2, True, False, False, 3, False, False, False, 0, 5),
    ]
    matrix = build_transition_matrix(rows)
    pre = BaseOutState(2, True, False, False)
    assert set(matrix[pre]) == {TERMINAL}
    assert matrix[pre][TERMINAL] == pytest.approx(1.0)


def test_rejects_outs_decreasing():
    # Outs can never decrease within a half-inning -- a row claiming
    # post_outs < pre_outs indicates a real upstream bug, not a case to
    # silently absorb.
    rows = [TransitionCountRow(1, False, False, False, 0, False, False, False, 0, 1)]
    with pytest.raises(MarkovError, match="outs decreased"):
        build_transition_matrix(rows)


def test_rejects_more_movers_than_possible_occupants():
    # Bases empty, 0 outs (only the batter can possibly move) can never
    # produce 2 runs scored plus a runner left on base -- that's 3 people
    # accounted for from a state that only ever had 1 (the batter).
    rows = [
        TransitionCountRow(0, False, False, False, 0, True, False, False, 2, 1),
    ]
    with pytest.raises(MarkovError, match="more people ended up"):
        build_transition_matrix(rows)


def test_rejects_negative_row_count():
    rows = [TransitionCountRow(0, False, False, False, 0, True, False, False, 0, -1)]
    with pytest.raises(MarkovError, match="negative row count"):
        build_transition_matrix(rows)


def test_rejects_post_outs_above_three():
    rows = [TransitionCountRow(2, False, False, False, 4, False, False, False, 0, 1)]
    with pytest.raises(MarkovError, match="post_outs > 3"):
        build_transition_matrix(rows)


def test_immediate_expected_runs_is_the_count_weighted_average():
    # From state (0, empty): 3 rows scoring 0 runs, 1 row scoring 2 runs.
    # Hand-computed: (3*0 + 1*2) / 4 = 0.5.
    rows = [
        TransitionCountRow(0, False, False, False, 1, False, False, False, 0, 3),
        TransitionCountRow(0, False, False, False, 0, True, True, False, 2, 1),
    ]
    immediate = markov._immediate_expected_runs(rows)
    pre = BaseOutState(0, False, False, False)
    assert immediate[pre] == pytest.approx(0.5)


def test_run_expectancy_solves_a_two_level_chain_by_hand():
    # A small, hand-solvable dependency chain, isolated from the other 22
    # transient states (every other state goes straight to TERMINAL for 0
    # runs with certainty, so its RE is trivially 0 and doesn't interfere):
    #
    # C = (2 outs, runner on 1st): 30% -> scores 1 run, ends the inning;
    #     70% -> scores 0, ends the inning.
    #     RE(C) = 0.3*(1+0) + 0.7*(0+0) = 0.3
    # D = (1 out, runner on 1st): 40% -> advances to C (0 immediate runs);
    #     60% -> double play, ends the inning (0 runs).
    #     RE(D) = 0.4*(0+RE(C)) + 0.6*(0+0) = 0.4*0.3 = 0.12
    c = BaseOutState(2, True, False, False)
    d = BaseOutState(1, True, False, False)

    matrix = {state: {TERMINAL: 1.0} for state in markov.TRANSIENT_STATES}
    immediate_runs = dict.fromkeys(markov.TRANSIENT_STATES, 0.0)

    matrix[c] = {TERMINAL: 1.0}
    immediate_runs[c] = 0.3  # E[runs] = 0.3*1 + 0.7*0
    matrix[d] = {c: 0.4, TERMINAL: 0.6}
    immediate_runs[d] = 0.0  # no runs score on the play itself, only later

    re = run_expectancy(matrix, immediate_runs)

    assert re[c] == pytest.approx(0.3)
    assert re[d] == pytest.approx(0.12)
    # Every other state was wired straight to TERMINAL for 0 runs.
    for state in markov.TRANSIENT_STATES:
        if state not in (c, d):
            assert re[state] == pytest.approx(0.0)


def test_run_expectancy_is_never_negative():
    matrix = {state: {TERMINAL: 1.0} for state in markov.TRANSIENT_STATES}
    immediate_runs = dict.fromkeys(markov.TRANSIENT_STATES, 0.0)
    re = run_expectancy(matrix, immediate_runs)
    assert all(value >= 0.0 for value in re.values())
