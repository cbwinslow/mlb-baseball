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
from mlb_baseball.model.markov.core import _immediate_expected_runs


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
    with pytest.raises(MarkovError, match="non-positive row count"):
        build_transition_matrix(rows)


def test_rejects_post_outs_above_three():
    rows = [TransitionCountRow(2, False, False, False, 4, False, False, False, 0, 1)]
    with pytest.raises(MarkovError, match="post_outs > 3"):
        build_transition_matrix(rows)


def test_immediate_expected_runs_is_the_count_weighted_average():
    # From state (0, empty): 3 rows scoring 0 runs (a strikeout -- only
    # the batter can possibly move from an empty-bases state, and they
    # made an out), 1 row scoring 1 run (a leadoff home run -- the only
    # way to score more than 0 from this exact state in a single play,
    # since there are no pre-existing runners to also drive in).
    # Hand-computed: (3*0 + 1*1) / 4 = 0.25.
    rows = [
        TransitionCountRow(0, False, False, False, 1, False, False, False, 0, 3),
        TransitionCountRow(0, False, False, False, 0, False, False, False, 1, 1),
    ]
    immediate = _immediate_expected_runs(rows)
    pre = BaseOutState(0, False, False, False)
    assert immediate[pre] == pytest.approx(0.25)


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


def test_rejects_zero_row_count():
    # PR review finding: `row.n < 0` let n=0 through, which would divide
    # by zero in build_transition_matrix if a pre-state's only rows all
    # had n=0. The real SQL always produces n >= 1 (a COUNT(*) GROUP BY
    # row can't exist with zero members), but build_transition_matrix
    # accepts arbitrary rows, so this is a real boundary to validate.
    rows = [TransitionCountRow(0, False, False, False, 0, True, False, False, 0, 0)]
    with pytest.raises(MarkovError, match="non-positive row count"):
        build_transition_matrix(rows)


def test_rejects_pre_outs_out_of_range():
    # PR review finding: pre_outs=3 (or negative) passed validation
    # silently, produced a BaseOutState not in TRANSIENT_STATES, and was
    # silently skipped by run_expectancy instead of being rejected.
    rows = [TransitionCountRow(3, False, False, False, 3, False, False, False, 0, 1)]
    with pytest.raises(MarkovError, match="invalid pre_outs"):
        build_transition_matrix(rows)


def test_immediate_expected_runs_validates_rows_independently():
    # _immediate_expected_runs is called directly in estimate_run_expectancy
    # alongside build_transition_matrix, but as its own public-ish function
    # (imported and tested directly like every other _-prefixed helper in
    # this file) it must not skip validation just because a caller didn't
    # also call build_transition_matrix first.
    rows = [TransitionCountRow(0, False, False, False, 1, False, False, False, 0, -1)]
    with pytest.raises(MarkovError, match="non-positive row count"):
        _immediate_expected_runs(rows)


def test_run_expectancy_raises_markov_error_on_singular_matrix():
    # A row-stochastic Q with a row summing to exactly 1.0 at the diagonal
    # (state transitions to itself with certainty, forever) makes (I - Q)
    # singular -- numpy.linalg.solve would raise a raw LinAlgError; this
    # must surface as a clean, catchable MarkovError instead.
    state = next(iter(markov.TRANSIENT_STATES))
    matrix = {state: {state: 1.0}}
    immediate_runs = {state: 0.0}
    with pytest.raises(MarkovError, match="singular"):
        run_expectancy(matrix, immediate_runs)


def test_estimate_transition_matrix_rejects_empty_seasons():
    with pytest.raises(ValueError, match="seasons"):
        markov.estimate_transition_matrix(object(), seasons=[])
